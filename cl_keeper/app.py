from __future__ import annotations

import datetime
import enum
import json
import logging
import os
import pathlib
import re
import tomllib
import typing as _t

import packaging.version
import semver
import yuio.app
import yuio.complete
import yuio.git
import yuio.io
import yuio.parse
import yuio.theme
from markdown_it.tree import SyntaxTreeNode

from cl_keeper._version import __version__
from cl_keeper.check import check as _check
from cl_keeper.config import (
    PYTHON_PRESET,
    Config,
    GlobalConfig,
    LinkTemplates,
    VersionFormat,
)
from cl_keeper.context import Context, IssueCode, IssueScope
from cl_keeper.fix import fix as _fix
from cl_keeper.model import (
    Changelog,
    ReleaseSection,
    RepoVersion,
    Section,
    SubSection,
    SubSectionCategoryKind,
    UnreleasedSection,
    Version,
)
from cl_keeper.parse import canonize_version as _canonize_version
from cl_keeper.parse import detect_subsection_metadata as _detect_subsection_metadata
from cl_keeper.parse import parse as _parse
from cl_keeper.parse import parse_version as _parse_version
from cl_keeper.parse import split_into_sections as _split_into_sections
from cl_keeper.render import print_diff as _print_diff
from cl_keeper.render import render as _render
from cl_keeper.sort import merge_sections as _merge_sections
from cl_keeper.vcs import detect_origin as _detect_origin
from cl_keeper.vcs import get_repo_versions

logger = logging.getLogger(__name__)


_GLOBAL_OPTIONS: GlobalConfig = GlobalConfig()

_TRAILER_RE = re.compile(
    r"^\s*(?:\[(?P<group>[^]]*+)\])?\s*(?P<message>.*)$", re.MULTILINE | re.DOTALL
)
_COMMENT_RE = re.compile(r"\<\!\-\-.*?(\-\-\>|\Z)", re.MULTILINE | re.DOTALL)


@yuio.app.app(version=__version__)
def main(
    #: override path to the config file
    config_path: (
        _t.Annotated[
            pathlib.Path,
            yuio.parse.ExistingPath(extensions=[".toml", ".yaml", ".yml"]),
        ]
        | None
    ) = yuio.app.field(default=None, flags=["-c", "--config"], usage=yuio.OMIT),
    #: override path to the changelog file
    file: pathlib.Path | None = yuio.app.field(
        default=None,
        flags=["-i", "--input"],
        completer=yuio.complete.File(extensions=[".md"]),
        usage=yuio.OMIT,
    ),
    #: increase severity of all messages by one level
    strict: bool = yuio.app.field(default=False, usage=yuio.OMIT),
    #: config overrides
    cfg: Config = yuio.app.field(usage=yuio.OMIT),
):
    _GLOBAL_OPTIONS.config_path = config_path
    _GLOBAL_OPTIONS.strict = strict
    _GLOBAL_OPTIONS.file = file

    logging.getLogger("markdown_it").setLevel("WARNING")

    logger.debug("changelog keeper version %s", __version__)


main.description = """
a helper for maintaining changelog files that use `keep-a-changelog` format.

"""

main.epilog = """
# further help:

- to get help for a specific subcommand:

  ```sh
  chk <subcommand> --help
  ```

- online documentation: https://cl-keeper.readthedocs.io/.

- changelog format: https://keepachangelog.com/
"""


@main.subcommand
def check():
    """
    check contents of the changelog file.

    """

    config = _load_config()
    file = _locate_changelog(config)

    ctx = Context(
        file,
        file.read_text(),
        config,
        _GLOBAL_OPTIONS.strict,
        _make_link_templates(file.parent, config),
    )

    repo_versions = None
    if ctx.config.check_repo_tags:
        repo_versions = get_repo_versions(file.parent, ctx)

    _check(_parse(ctx), ctx, repo_versions)

    if ctx.has_messages():
        ctx.report()
        ctx.exit_if_has_errors()
    else:
        yuio.io.success("No issues detected")


@main.subcommand
def fix(
    #: don't save changes, print the diff instead
    dry_run: bool = False,
    #: print diff
    diff: bool = False,
):
    """
    fix contents of the changelog file.

    """

    config = _load_config()
    file = _locate_changelog(config)
    original = file.read_text()

    ctx = Context(
        file,
        original,
        config,
        _GLOBAL_OPTIONS.strict,
        _make_link_templates(file.parent, config),
    )

    repo_versions = None
    if ctx.config.check_repo_tags:
        repo_versions = get_repo_versions(file.parent, ctx)

    changelog = _parse(ctx)
    _fix(changelog, ctx, repo_versions)

    result = _render(changelog, ctx)

    ctx.reset(result)

    _check(_parse(ctx), ctx, repo_versions)

    if result == original and ctx.has_messages():
        yuio.io.success("No fixable issues detected")
    elif result == original:
        yuio.io.success("No issues detected")
    elif not dry_run:
        yuio.io.success("Changelog successfully fixed")
        file.write_text(result)

    if ctx.has_messages():
        yuio.io.heading("Unfixed issues")
        ctx.report()

    if dry_run or diff:
        _print_diff(original, result, file)


class BumpMode(enum.Enum):
    AUTO = "auto"
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    POST = "post"

    def __str__(self) -> str:
        return self.value


_PRE_RELEASE_GROUP = yuio.app.MutuallyExclusiveGroup()


@main.subcommand
def bump(
    #: produce result even if errors are detected
    ignore_errors: bool = False,
    #: don't save changes, print the diff instead
    dry_run: bool = False,
    #: release version or tag that will be used for a new release
    version: (
        _t.Annotated[BumpMode, yuio.parse.WithMeta(desc="version component")]
        | str
        | None
        | yuio.git.Tag
    ) = yuio.app.positional(default=None),
    #: create an alpha pre-release. If `version` is given, this will bump
    #: the corresponding component and make a pre-release. If `version` is not given,
    #: the latest release must be a pre-release itself.
    alpha: bool = yuio.app.field(default=False, group=_PRE_RELEASE_GROUP),
    #: create a beta pre-release, similar to `--alpha`.
    beta: bool = yuio.app.field(default=False, group=_PRE_RELEASE_GROUP),
    #: create a release candidate, similar to `--alpha`.
    rc: bool = yuio.app.field(default=False, group=_PRE_RELEASE_GROUP),
    #: open generated changes for editing
    edit: bool = False,
    #: commit and tag the release after updating changelog.
    commit: bool = False,
):
    """
    move entries from `unreleased` to a new release.

    """

    if version is None and not alpha and not beta and not rc:
        raise yuio.parse.ParsingError(
            "<version> is required when --alpha, --beta, and --rc are not specified"
        )
    if isinstance(version, str) and (alpha or beta or rc):
        raise yuio.parse.ParsingError(
            "--alpha, --beta, --rc are not allowed when specifying custom versions"
        )

    config = _load_config()
    file = _locate_changelog(config)
    original = file.read_text()

    if commit:
        repo = yuio.git.Repo(file.parent)
        status = repo.status()
        if status.cherry_pick_head:
            raise yuio.app.AppError("Can't bump changelog: cherry pick is in progress")
        if status.merge_head:
            raise yuio.app.AppError("Can't bump changelog: merge is in progress")
        if status.rebase_head:
            raise yuio.app.AppError("Can't bump changelog: rebase is in progress")
        if status.revert_head:
            raise yuio.app.AppError("Can't bump changelog: revert is in progress")
        if not status.branch:
            raise yuio.app.AppError("Can't bump changelog: git head is detached")

    ctx = Context(
        file,
        original,
        config,
        _GLOBAL_OPTIONS.strict,
        _make_link_templates(file.parent, config),
    )

    if isinstance(version, str) and version.startswith(config.tag_prefix):
        version = version[len(config.tag_prefix) :]

    changelog = _parse(ctx)

    found = None
    to_remove = set()
    for i, section, _ in _find_sections(FindMode.UNRELEASED, changelog, config):
        to_remove.add(i)
        if found is None:
            found = section
        else:
            _merge_sections(found, section)

    changelog.sections = [
        section for i, section in enumerate(changelog.sections) if i not in to_remove
    ]

    if found is None:
        found = UnreleasedSection(
            heading=None, subsections=[], version_link=None, version_label=None
        )

    repo_versions = None
    if isinstance(version, BumpMode) or version is None:
        repo_versions = get_repo_versions(file.parent, ctx)
        latest_version, _, _ = _find_latest_version(changelog, repo_versions, config)
        if latest_version is None:
            raise yuio.app.AppError("No previous release to bump")
        version = _bump_version(latest_version, version, alpha, beta, rc, found, config)
    else:
        if ctx.config.check_repo_tags:
            repo_versions = get_repo_versions(file.parent, ctx)

    parsed_version = _parse_version(version, ctx.config)
    if parsed_version is None and config.version_format is not VersionFormat.NONE:
        ctx.issue(
            IssueCode.INVALID_VERSION,
            "New version `%s` doesn't follow %s specification",
            version,
            ctx.config.version_format.value,
            scope=IssueScope.EXTERNAL,
        )

    _check(changelog, ctx, repo_versions)

    if ctx.has_errors():
        ctx.report()
    if not ignore_errors:
        ctx.exit_if_has_errors()

    for _, section, _ in _find_sections(version, changelog, config):
        if section.map is not None:
            pos = f" on line `{section.map[0] + 1}`"
        else:
            pos = ""
        raise yuio.app.AppError(f"release {version} already exists{pos}")

    new_section = ReleaseSection(
        heading=None,
        subsections=found.subsections,
        version=version,
        parsed_version=parsed_version,
        canonized_version=_canonize_version(parsed_version, config) or version,
        release_date=datetime.date.today(),
        version_link=None,
        version_label=None,
        release_date_fmt=datetime.date.today().isoformat(),
        release_comment=None,
    )

    if edit:
        _edit_section(changelog, ctx, new_section)

    changelog.sections.append(
        UnreleasedSection(
            heading=None, subsections=[], version_link=None, version_label=None
        )
    )
    changelog.sections.append(new_section)

    _fix(changelog, ctx, repo_versions)

    result = _render(changelog, ctx)

    if not dry_run:
        yuio.io.success("Changelog successfully updated")
        file.write_text(result)
    else:
        _print_diff(original, result, file)

    if commit:
        yuio.io.heading("Commit")
    if ctx.has_errors() and commit:
        yuio.io.warning("Not committing changes: errors detected")
        ctx.exit_if_has_errors()
    tag = f"{config.tag_prefix}{version}"
    if commit and not dry_run:
        repo = yuio.git.Repo(file.parent)
        repo.git("add", str(file))
        repo.print_status()
        yuio.io.info(
            "You can take a look around and make any changes before proceeding.\n"
            "Alternatively, you can cancel now and make a release commit later.\n"
        )
        ok = yuio.io.ask[bool]("Proceed with commit and tag?", default=False)
        message = f"Release {version}"
        if not ok:
            yuio.io.failure("Commit canceled")
            yuio.io.md(
                """
                Use this command to commit changes:

                ```sh
                git commit -m '%s'
                git tag %s
                ```
                """,
                message,
                tag,
            )
            raise yuio.app.AppError()
        repo.git("commit", "-m", message)
        repo.git("tag", tag)
        status = repo.status()
        yuio.io.success("Created commit `%s` and tag `%s`.", status.commit, tag)
        yuio.io.md(
            """
            Use `git commit --amend` and `git tag` to update commit contents or message:

            ```sh
            git commit --amend && git tag -f %s
            ```
            """,
            tag,
        )
    if commit and dry_run:
        yuio.io.success("Dry-run: not committing and creating tag `%s`", tag)


bump.usage = """
%(prog)s [<options>] [--ignore-errors] [--dry-run] [--edit] <version>
%(prog)s [<options>] [--ignore-errors] [--dry-run] [--edit] [auto|major|minor|patch|post] [--alpha|--beta|--rc]
"""

bump.epilog = """
# examples:

## specifying version manually

you can always supply a specific version for a new release. As long as there are no
prior releases with the same version, this operation will succeed:

```sh
chk bump 1.0.5
```

## automatic version detection

changelog keeper can suggest next version based on changelog content
(the `--dry-run` flag is handy here):

```sh
chk bump auto
```

## bumping a version component

you can bump a version component by setting `<version>` to `major`, `minor`,
`patch`, or `post`:

```sh
chk bump minor  # 1.0.0 -> 1.1.0
```

## pre-releases

you can make a pre-release by adding `--alpha`, `--beta`, or `--rc`:

```sh
chk bump major --beta  # 1.5.1 -> 2.0.0b0
```

if the last release is a pre-release itself, you can bump its pre-release version
component:

```sh
chk bump --beta  # 1.0.0b0 -> 1.0.0b1
chk bump --rc  # 1.0.0b0 -> 1.0.0rc0
```

"""


class FindMode(enum.Enum):
    LATEST = "latest"
    UNRELEASED = "unreleased"

    def __str__(self) -> str:
        return self.value


@main.subcommand
def find(
    #: produce result even if errors are detected
    ignore_errors: bool = False,
    #: print data in JSON format
    format_json: bool = yuio.app.field(default=False, flags="--json"),
    #: release version or tag, can also be `unreleased` or `latest`
    version: (
        _t.Annotated[FindMode, yuio.parse.WithMeta(desc="query")] | str | yuio.git.Tag
    ) = yuio.app.positional(),
):
    """
    find a changelog entry for a given release version.

    """

    config = _load_config()
    file = _locate_changelog(config)
    original = file.read_text()

    if isinstance(version, str):
        version = version.removeprefix("refs/tags/").removeprefix(config.tag_prefix)

    ctx = Context(
        file,
        original,
        config,
        _GLOBAL_OPTIONS.strict,
        _make_link_templates(file.parent, config),
    )

    repo_versions = None
    if ctx.config.check_repo_tags:
        repo_versions = get_repo_versions(file.parent, ctx)

    changelog = _parse(ctx)

    _check(changelog, ctx, repo_versions)

    if ctx.has_errors():
        ctx.report()
    if not ignore_errors:
        ctx.exit_if_has_errors()

    found = None
    found_latest_in_changelog = None
    for _, section, is_latest in _find_sections(version, changelog, config):
        if found is None:
            found = section
            found_latest_in_changelog = is_latest
        else:
            _merge_sections(found, section)

    if found is None and isinstance(version, str):
        parsed_version = _parse_version(version, config)
        canonized_version = _canonize_version(parsed_version, config) or version

        lower_bound = ctx.config.parsed_ignore_missing_releases_before
        regex_bound = ctx.config.ignore_missing_releases_regexp

        if (repo_versions is None or canonized_version in repo_versions) and (
            (lower_bound and parsed_version and parsed_version < lower_bound)
            or (regex_bound is not None and re.search(regex_bound, version))
        ):
            found = ReleaseSection(
                heading=None,
                subsections=[],
                version=version,
                parsed_version=parsed_version,
                canonized_version=canonized_version,
                version_link=None,
                version_label=None,
                release_date=None,
                release_date_fmt=None,
                release_comment=None,
            )

    if found is not None:
        tokens = found.to_tokens(include_heading=False)
        if format_json:
            found_version = None
            found_canonized_version = None
            found_latest = None
            tag = None
            is_pre_release = None
            is_post_release = None
            if release := found.as_release():
                found_version = release.version
                found_canonized_version = release.canonized_version
                if repo_versions and (
                    repo_version := repo_versions.get(release.canonized_version)
                ):
                    tag = f"{config.tag_prefix}{repo_version.version}"
                is_pre_release = _is_pre_release(release.parsed_version)
                is_post_release = _is_post_release(release.parsed_version)
                try:
                    _, _, latest_version_canonized = _find_latest_version(
                        changelog, repo_versions, config
                    )
                except:
                    pass
                else:
                    found_latest = release.canonized_version == latest_version_canonized
            data = {
                "version": found_version,
                "canonizedVersion": found_canonized_version,
                "tag": tag,
                "text": _render(changelog, ctx, tokens, disable_wrapping=True),
                "isLatestInChangelog": found_latest_in_changelog,
                "isLatestInSemanticOrder": found_latest,
                "isPreRelease": is_pre_release,
                "isPostRelease": is_post_release,
                "isUnreleased": found.is_unreleased(),
            }
            print(json.dumps(data, indent="  "))
        else:
            print(_render(changelog, ctx, tokens, disable_wrapping=True), end="")
    else:
        raise yuio.app.AppError("Can't find changelog entry for version `%s`", version)


find.usage = """
%(prog)s [<options>] [--ignore-errors] [--json] <version>
%(prog)s [<options>] [--ignore-errors] [--json] {latest|unreleased}
"""


find.epilog = """
# examples:

find an exact version:

```sh
chk find v1.0.0-rc2
```

find the first version (barring the `unreleased` section)
that appears in the changelog:

```sh
chk find latest
```

find the `unreleased` section:

```sh
chk find unreleased
```

# json output:

If `--json` flag is given, a JSON object is printed to stdout. It will contain
the following fields:

- <c hl/flag:sh-usage>version</c> - version string, as appears in the changelog.

  Can be `null` if unreleased section is requested.

- <c hl/flag:sh-usage>canonizedVersion</c> - version string, canonized according to the used
  `version_format`.

  If `version_format` is `null` or canonization fails, this will contain
  string from `version`.

- <c hl/flag:sh-usage>tag</c> - tag that corresponds to this version.

  Can be `null` if requested release not found, if unreleased section is requested,
  if `check_repo_tags` is `false`, if version canonization fails, or if tag is not
  found for this release.

- <c hl/flag:sh-usage>text</c> - text extracted from the changelog entry.

  Can be empty if requested release not found.

- <c hl/flag:sh-usage>isLatestInChangelog</c> - `true` if found version appears first in the changelog file.

  Can be `null` if requested release not found, or if unreleased section
  is requested.

- <c hl/flag:sh-usage>isLatestInSemanticOrder</c> - `true` if this is the latest known release.

  Release versions are compared with respect to the selected `version_format`.
  If `check_repo_tags` is `true`, this flag also checks all tags found
  in the repository.

  Can be `null` if requested release not found, or if unreleased section
  is requested.

- <c hl/flag:sh-usage>isPreRelease</c> - `true` if release version contains a pre-release component,
  like `beta` or `rc`.

  Can be `null` if requested release not found, if unreleased section
  is requested, or if version canonization fails.

- <c hl/flag:sh-usage>isPostRelease</c> - `true` if release version contains a post-release component.

  Can be `null` if requested release not found, if unreleased section
  is requested, or if version canonization fails.

- <c hl/flag:sh-usage>isUnreleased</c> - `true` if unreleased section is requested.

"""


@main.subcommand
def check_tag(
    #: full name of the tag to check
    tag: yuio.git.Tag | str = yuio.app.positional(),
):
    """
    check if a git tag conforms to the versioning specification.

    this command is handy to use in release CI or in a pre-push git hook to verify
    that all tags conform to the selected versioning specification.

    """

    config = _load_config()
    error = False
    if not tag.startswith(config.tag_prefix):
        yuio.io.error("Tag `%s` should start with `%r`", tag, config.tag_prefix)
        error = True
    parsed = _parse_version(tag.removeprefix(config.tag_prefix), config)
    if not parsed:
        yuio.io.error(
            "Tag `%s` does not follow %s specification",
            tag,
            config.version_format.value,
        )
        error = True
    if error:
        raise yuio.app.AppError("Tag verification failed")
    else:
        yuio.io.success("Tag `%s` is valid", tag)


@main.subcommand(help=yuio.DISABLED)
def pre_commit_check(
    diff: bool = False, changed_files: set[pathlib.Path] = yuio.app.positional()
):
    """
    same as `fix`, but expects list of changed files as command line arguments,
    and doesn't perform fix if changelog is not updated.

    """
    config = _load_config()
    file = _locate_changelog(config)

    if file not in changed_files and (
        _GLOBAL_OPTIONS.config_path is None
        or _GLOBAL_OPTIONS.config_path not in changed_files
    ):
        return

    fix.command(diff=diff)


@main.subcommand(help=yuio.DISABLED)
def pre_commit_check_tag():
    """
    same as `check-tag`, but tag is supplied via `PRE_COMMIT_REMOTE_BRANCH` env var.

    """
    remote_branch = os.environ.get("PRE_COMMIT_REMOTE_BRANCH")
    if not remote_branch:
        return
    config = _load_config()
    prefix = f"refs/tags/{config.tag_prefix}"
    if not remote_branch.startswith(prefix):
        return
    check_tag.command(remote_branch.removeprefix("refs/tags/"))


def _load_config() -> Config:
    config = Config()
    if _GLOBAL_OPTIONS.config_path is None:
        root = _GLOBAL_OPTIONS.file or pathlib.Path.cwd()
        while root:
            changelog_toml = root.joinpath(".changelog.toml")
            changelog_toml_exists = changelog_toml.exists()
            changelog_yaml = root.joinpath(".changelog.yaml")
            changelog_yaml_exists = changelog_yaml.exists()
            changelog_yml = root.joinpath(".changelog.yml")
            changelog_yml_exists = changelog_yml.exists()
            pyproject_toml = root.joinpath("pyproject.toml")
            pyproject_toml_exists = pyproject_toml.exists()

            if changelog_toml_exists + changelog_yaml_exists + changelog_yml_exists > 1:
                found = ", ".join(
                    f"<c path>{file}</c>"
                    for file, exists in [
                        (changelog_toml, changelog_toml_exists),
                        (changelog_yaml, changelog_yaml_exists),
                        (changelog_yml, changelog_yml_exists),
                    ]
                    if exists
                )
                raise yuio.app.AppError(f"Found multiple config files: {found}")
            if changelog_toml_exists:
                _GLOBAL_OPTIONS.config_path = changelog_toml
                break
            elif changelog_yaml_exists:
                _GLOBAL_OPTIONS.config_path = changelog_yaml
                break
            elif changelog_yml_exists:
                _GLOBAL_OPTIONS.config_path = changelog_yml
                break
            elif pyproject_toml_exists:
                _GLOBAL_OPTIONS.config_path = pyproject_toml
                break
            next_root = root.parent
            if next_root == root:
                break
            root = next_root
        if _GLOBAL_OPTIONS.config_path is None:
            logger.info("using default config")
            logger.debug("config = %r", config)
            return config
        else:
            logger.debug("found config %s", _GLOBAL_OPTIONS.config_path)
    else:
        logger.debug("loading config %s", _GLOBAL_OPTIONS.config_path)

    if not _GLOBAL_OPTIONS.config_path.exists():
        raise yuio.app.AppError(
            "Config file <c path>%s</c> doesn't exist", _GLOBAL_OPTIONS.config_path
        )
    if not _GLOBAL_OPTIONS.config_path.is_file():
        raise yuio.app.AppError(
            "Config path <c path>%s</c> is not a file", _GLOBAL_OPTIONS.config_path
        )
    if _GLOBAL_OPTIONS.config_path.name == "pyproject.toml":
        config.update(PYTHON_PRESET)
        try:
            data = tomllib.loads(_GLOBAL_OPTIONS.config_path.read_text())
        except tomllib.TOMLDecodeError as e:
            yuio.io.warning(
                "Failed to parse config file <c path>%s</c>: %s",
                _GLOBAL_OPTIONS.config_path,
                e,
            )
            logger.debug("config = %r", config)
            return config
        try:
            data = data["tool"]["cl_keeper"]
        except KeyError as e:
            logger.debug(
                "%s doesn't have section tool.cl_keeper",
                _GLOBAL_OPTIONS.config_path,
            )
            logger.info("using config from %s", _GLOBAL_OPTIONS.config_path)
            logger.debug("config = %r", config)
            return config

        config.update(
            Config.load_from_parsed_file(data, path=_GLOBAL_OPTIONS.config_path)
        )
    elif _GLOBAL_OPTIONS.config_path.suffix == ".toml":
        config.update(Config.load_from_toml_file(_GLOBAL_OPTIONS.config_path))
    elif _GLOBAL_OPTIONS.config_path.suffix in [".yaml", ".yml"]:
        config.update(Config.load_from_yaml_file(_GLOBAL_OPTIONS.config_path))
    else:
        raise yuio.app.AppError(
            "Unknown config format `%s`: <c path>%s</c>",
            _GLOBAL_OPTIONS.config_path.suffix,
            _GLOBAL_OPTIONS.config_path,
        )

    logger.info("using config from %s", _GLOBAL_OPTIONS.config_path)
    logger.debug("config = %r", config)
    return config


def _locate_changelog(config: Config) -> pathlib.Path:
    if (file := _GLOBAL_OPTIONS.file) is None:
        if _GLOBAL_OPTIONS.config_path is None:
            file = config.file
        else:
            file = _GLOBAL_OPTIONS.config_path.parent / config.file
    file = file.expanduser().resolve()
    if not file.exists():
        raise yuio.app.AppError("File `%s` doesn't exist", file)
    if not file.is_file():
        raise yuio.app.AppError("Path `%s` is not a file", file)
    return file


def _make_link_templates(repo_root: pathlib.Path, config: Config) -> LinkTemplates:
    if not config.add_release_link:
        return LinkTemplates("", "", "", {})

    link_templates = LinkTemplates(
        config.release_link_template or "",
        config.release_link_template_last or "",
        config.release_link_template_first or "",
        config.release_link_template_vars or {},
    )

    if link_templates.has_unresolved_links() and config.release_link_preset:
        link_templates.update(config.release_link_preset.get_links())

    if link_templates.has_unresolved_links():
        logger.debug("link templates are not set, trying to detect repo url from git")
        origin = _detect_origin(repo_root)
        if origin:
            link_templates.update(origin)
        else:
            raise yuio.app.AppError(
                "Can't detect url to use in link templates. Please, set "
                "`release_link_preset` or `release_link_template`, "
                "`release_link_template_last`, `release_link_template_first` "
                "in config. Alternatively, set `add_release_link` to `false`"
            )

    logger.debug("link_templates = %r", link_templates)

    _check_link_templates(link_templates)

    return link_templates


def _check_link_templates(link_templates: LinkTemplates):
    class _UnknownKeyDetector:
        def __init__(self, vars: dict[str, str]) -> None:
            self._vars = vars
            self.unknown_keys: set[str] = set()

        def __getitem__(self, key: str) -> str:
            if key not in ["tag", "prev_tag"] and key not in self._vars:
                self.unknown_keys.add(key)
            return ""

    mapping = _UnknownKeyDetector(link_templates.vars)
    link_templates.template.format_map(mapping)
    link_templates.template_first.format_map(mapping)
    link_templates.template_last.format_map(mapping)
    if mapping.unknown_keys:
        yuio.io.error(
            "Some variables used in link templates are missing "
            "from `release_link_template_vars`: `%s`. Please, add them to config",
            ", ".join(sorted(mapping.unknown_keys)),
        )
        raise yuio.app.AppError("Configuration is incorrect")


def _find_sections(version: FindMode | str, changelog: Changelog, config: Config):
    canonized_version = None
    if isinstance(version, str):
        canonized_version = (
            _canonize_version(_parse_version(version, config), config) or version
        )
    logger.debug(
        "searching for release %r, canonized_version=%r", version, canonized_version
    )
    is_latest = True
    for i, section in enumerate(changelog.sections):
        if section.is_unreleased():
            logger.debug("checking unreleased section")
            if version is FindMode.UNRELEASED:
                yield i, section, None
        elif release := section.as_release():
            logger.debug("checking release %r", release.version)
            if version is FindMode.LATEST or (
                release.canonized_version == canonized_version
            ):
                yield i, section, is_latest
                if version is FindMode.LATEST:
                    version = release.version
                    canonized_version = release.canonized_version
            is_latest = False


def _edit_section(changelog: Changelog, ctx: Context, section: Section):
    logger.debug("external edit for %s", section.what())
    to_edit = (
        "<!--\n"
        f" Edit changelog for {section.what()}.\n"
        " An empty changelog aborts the command.\n"
        "-->\n\n"
    )
    to_edit += _render(changelog, ctx, section.to_tokens(include_heading=False))
    to_edit = yuio.io.edit(to_edit, comment_marker=None, file_ext=".md")
    to_edit = _COMMENT_RE.sub("", to_edit).strip()
    if not to_edit:
        raise yuio.app.AppError("Got an empty changelog, command aborted")
    else:
        content = changelog.parser.parse(to_edit, changelog.parser_env)
        root = SyntaxTreeNode(content)
        subsections: list[SubSection] = []
        for subheading, content in _split_into_sections(root.children, 3):
            subsection = SubSection(heading=subheading, content=content)
            _detect_subsection_metadata(subsection, ctx)
            subsections.append(subsection)
        section.subsections = subsections
        logger.debug("external edit successful")


def _find_latest_version(
    changelog: Changelog, repo_versions: dict[str, RepoVersion] | None, config: Config
) -> tuple[Version | None, str | None, str | None]:
    logger.debug("trying to determine the latest release")
    max_version = None
    max_version_str = None
    max_version_str_canonized = None
    for section in changelog.sections:
        release = section.as_release()
        if not release:
            continue
        if release.parsed_version is None:
            _report_latest_version_fail("release", release.version, release.map, config)
        logger.debug("checking release version %r", release.canonized_version)
        if max_version is None or release.parsed_version > max_version:
            max_version = release.parsed_version
            max_version_str = release.version
            max_version_str_canonized = release.canonized_version
    if repo_versions is not None:
        for data in repo_versions.values():
            if data.parsed_version is None:
                _report_latest_version_fail("release", data.version, None, config)
            logger.debug("checking tag %r", data.canonized_version)
            if max_version is None or data.parsed_version > max_version:
                max_version = data.parsed_version
                max_version_str = data.version
                max_version_str_canonized = data.canonized_version
    logger.debug("latest release is %r", max_version_str)
    return max_version, max_version_str, max_version_str_canonized


def _report_latest_version_fail(
    what: str, version: str | None, map: tuple[int, int] | None, config: Config
) -> _t.Never:
    if config.version_format is VersionFormat.NONE:
        reason = "`version_format` is set to `none`"
        args = ()
    else:
        reason = f"{what} `%s` "
        if map:
            reason += f"on line `{map[0] + 1}` "
        reason += "does not follow %s specification"
        args = (version, config.version_format.value)
    raise yuio.app.AppError(
        "Can't determine the latest version because " + reason, *args
    )


_PY_TO_SEMVER_PRE_RELEASE = {
    "a": "alpha",
    "alpha": "alpha",
    "b": "beta",
    "beta": "beta",
    "rc": "rc",
}


def _bump_version(
    version: Version,
    mode: BumpMode | None,
    alpha: bool,
    beta: bool,
    rc: bool,
    unreleased: Section,
    config: Config,
) -> str:
    if isinstance(version, packaging.version.Version):
        epoch = version.epoch
        major, minor, patch = tuple(
            version.release[i] if len(version.release) >= i else 0 for i in range(3)
        )
        pre = version.pre
        post = version.post
    elif isinstance(version, semver.Version):
        if mode is BumpMode.POST:
            raise yuio.app.AppError(
                "Semver schema doesn't support creating post releases",
            )
        epoch = 0
        major, minor, patch = version.major, version.minor, version.patch
        pre = _split_semver_prerelease(version.prerelease)
        post = None
    else:
        assert False
    if mode is BumpMode.AUTO:
        mode = _suggest_bump(unreleased, config)
    match mode:
        case BumpMode.MAJOR:
            major, minor, patch, pre, post = major + 1, 0, 0, None, None
        case BumpMode.MINOR:
            major, minor, patch, pre, post = major, minor + 1, 0, None, None
        case BumpMode.PATCH:
            major, minor, patch, pre, post = major, minor, patch + 1, None, None
        case BumpMode.POST:
            if pre is not None:
                raise yuio.app.AppError(
                    "Creating a post-release for a pre-release is probably "
                    "a mistake. Please, specify version manually if you're sure "
                    "you want to do this",
                    version,
                )
            if post is None:
                post = 0
            else:
                post += 1
        case BumpMode.AUTO:
            assert False
        case None:
            assert alpha or beta or rc
            if not pre:
                raise yuio.app.AppError(
                    "Can't create a pre-release without bumping "
                    "a primary version component: latest release `%s` "
                    "is not a pre-release",
                    version,
                )

    if (alpha or beta or rc) and pre and pre[0] not in _PY_TO_SEMVER_PRE_RELEASE:
        raise yuio.app.AppError(
            "Can't create a pre-release: latest release `%s` has "
            "unknown label `%r`. Please, specify version manually",
            version,
            pre[0],
        )
    elif alpha:
        if pre and pre[0] in ("a", "alpha"):
            pre = ("a", pre[1] + 1)
        elif pre:
            if pre[0] == "rc":
                what = "a release candidate"
            else:
                what = "a beta pre-release"
            raise yuio.app.AppError("Can't create an alpha pre-release after %s", what)
        else:
            pre = ("a", 0)
    elif beta:
        if pre and pre[0] in ("b", "beta"):
            pre = ("b", pre[1] + 1)
        elif pre and pre[0] == "rc":
            raise yuio.app.AppError(
                f"Can't create a beta pre-release after a release candidate"
            )
        else:
            pre = ("b", 0)
    elif rc:
        if pre and pre[0] == "rc":
            pre = ("rc", pre[1] + 1)
        else:
            pre = ("rc", 0)

    if isinstance(version, packaging.version.Version):
        if epoch > 0:
            prefix = f"{epoch}!"
        else:
            prefix = ""
        suffix = ""
        if pre:
            suffix += "".join(map(str, pre))
        if post is not None:
            suffix += f".post{post}"
        bumped = packaging.version.Version(f"{prefix}{major}.{minor}.{patch}{suffix}")
    else:
        suffix = ""
        if pre:
            pre_str = f"{_PY_TO_SEMVER_PRE_RELEASE[pre[0]]}{pre[1]}"
        else:
            pre_str = None
        bumped = semver.Version(major, minor, patch, pre_str)

    logger.debug(
        "performed version bump: mode=%r, alpha=%r, beta=%r, rc=%r, result=%r",
        mode,
        alpha,
        beta,
        rc,
        bumped,
    )

    canonical = _canonize_version(_t.cast(Version, bumped), config)
    assert canonical
    return canonical


_SEMVER_PRERELEASE_RE = re.compile(r"^([a-zA-Z0-9.-]*?)([0-9]*)$")


def _split_semver_prerelease(pre: str | None) -> tuple[str, int] | None:
    if pre is None:
        return None
    if match := _SEMVER_PRERELEASE_RE.match(pre):
        return match.group(1).rstrip(".-"), int(match.group(2))
    else:
        return pre, 0


def _suggest_bump(unreleased: Section, config: Config) -> BumpMode:
    logger.debug("checking change categories to determine appropriate version bump")
    has_major = has_minor = has_patch = False
    for subsection in unreleased.subsections:
        if subsection.category_kind != SubSectionCategoryKind.KNOWN:
            logger.debug(
                "skipping subsection %s: category unknown", subsection.category
            )
            continue
        logger.debug("inspecting subsection %s", subsection.category)
        if subsection.category in config.full_bump_major_categories:
            logger.debug("subsection warrants a major bump")
            has_major = True
        elif subsection.category in config.full_bump_minor_categories:
            logger.debug("subsection warrants a minor bump")
            has_minor = True
        elif subsection.category in config.full_bump_patch_categories:
            logger.debug("subsection warrants a patch bump")
            has_patch = True
    if has_major:
        return BumpMode.MAJOR
    elif has_minor:
        return BumpMode.MINOR
    elif has_patch:
        return BumpMode.PATCH
    else:
        raise yuio.app.AppError(
            "Can't determine which version component to bump: changelog for unreleased "
            "version doesn't have change categories from `bump_major_categories`, "
            "`bump_minor_categories`, or `bump_patch_categories`"
        )


def _is_pre_release(version: Version | None) -> bool | None:
    if version is None:
        return None
    elif isinstance(version, packaging.version.Version):
        return version.is_prerelease
    elif isinstance(version, semver.Version):
        return version.prerelease is not None
    else:
        assert False


def _is_post_release(version: Version | None) -> bool | None:
    if version is None:
        return None
    elif isinstance(version, packaging.version.Version):
        return version.is_postrelease
    elif isinstance(version, semver.Version):
        return False
    else:
        assert False


class Theme(yuio.theme.DefaultTheme):
    colors = {
        "code": "bold",
        "msg/text:report_error": ["red"],
        "msg/text:report_warning": ["yellow"],
        "msg/text:report_weak_warning": ["cyan"],
        "msg/text:report_info": ["cyan"],
    }


main.theme = Theme


if __name__ == "__main__":
    main.run()
