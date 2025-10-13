from __future__ import annotations

import datetime
import enum
import logging
import pathlib
import re
import tomllib
import typing as _t

import packaging.version
import semver
import yuio.app
import yuio.git
import yuio.io
import yuio.parse
import yuio.theme
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode

from changelog_keeper._version import __version__
from changelog_keeper.check import check as _check
from changelog_keeper.config import (
    PYTHON_PRESET,
    Config,
    GlobalConfig,
    LinkTemplates,
    TagFormat,
)
from changelog_keeper.context import Context, IssueCode, IssueScope
from changelog_keeper.fix import fix as _fix
from changelog_keeper.model import (
    Changelog,
    RepoVersion,
    Section,
    SectionType,
    SubSection,
    SubSectionType,
    Version,
)
from changelog_keeper.parse import canonize_version as _canonize_version
from changelog_keeper.parse import (
    detect_subsection_metadata as _detect_subsection_metadata,
)
from changelog_keeper.parse import parse as _parse
from changelog_keeper.parse import parse_version as _parse_version
from changelog_keeper.parse import split_into_sections as _split_into_sections
from changelog_keeper.render import print_diff as _print_diff
from changelog_keeper.render import render as _render
from changelog_keeper.sort import merge_sections as _merge_sections
from changelog_keeper.vcs import detect_origin as _detect_origin
from changelog_keeper.vcs import get_repo_versions

logger = logging.getLogger(__name__)


_GLOBAL_OPTIONS: GlobalConfig = GlobalConfig()

_TRAILER_RE = re.compile(
    r"^\s*(?:\[(?P<group>[^]]*+)\])?\s*(?P<message>.*)$", re.MULTILINE
)
_COMMENT_RE = re.compile(r"\<\!\-\-.*?(\-\-\>|\Z)", re.MULTILINE | re.DOTALL)


@yuio.app.app(version=__version__)
def main(
    #: global options
    global_options: GlobalConfig = yuio.app.inline(help=""),
):

    _GLOBAL_OPTIONS.update(global_options)

    logging.getLogger("markdown_it").setLevel("WARNING")


main.usage = """
%(prog)s [--config <*.toml>] [--strict] [-v] <subcommand>
""".strip()

main.description = """
a helper for maintaining changelog files that use `keep-a-changelog` format.

"""

main.epilog = """
# further help:

- to get help for a specific subcommand:

  ```sh
  chk <subcommand> --help
  ```

- online documentation: https://changelog-keeper.readthedocs.io/.
  Alternatively, check out

  ```sh
  man chk
  ```

- changelog format: https://keepachangelog.com/
"""


@main.subcommand
def check(
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.field(default=None, flags=["-i", "--input"]),
):
    """
    check contents of the changelog file.

    """

    config = _load_config(file)
    file = _locate_changelog(file, config)

    ctx = Context(
        file,
        file.read_text(),
        config,
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
        yuio.io.success("<c b>No errors detected</c>")


@main.subcommand
def fix(
    #: don't save changes, print the diff instead
    dry_run: bool = False,
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.field(default=None, flags=["-i", "--input"]),
):
    """
    fix contents of the changelog file.

    """

    config = _load_config(file)
    file = _locate_changelog(file, config)
    original = file.read_text()

    ctx = Context(
        file,
        original,
        config,
        _make_link_templates(file.parent, config),
    )

    repo_versions = None
    if ctx.config.check_repo_tags:
        repo_versions = get_repo_versions(file.parent, ctx)

    changelog = _parse(ctx)
    _fix(changelog, ctx, repo_versions)

    result = _render(changelog, ctx)

    if result == original:
        yuio.io.success("<c b>No errors detected</c>")
        return

    if not dry_run:
        yuio.io.success("<c b>Changelog successfully fixed</c>")
        file.write_text(result)
    else:
        yuio.io.success("<c b>Dry-run complete</c>")

    ctx.reset(result)

    _check(_parse(ctx), ctx, repo_versions)

    if ctx.has_messages():
        yuio.io.heading("Some issues can't be fixed automatically")
        ctx.report()

    if dry_run:
        _print_diff(original, result, file)

    ctx.exit_if_has_errors()


@main.subcommand
def gen(
    #: produce result even if errors are detected
    ignore_errors: bool = False,
    #: don't save changes, print the diff instead
    dry_run: bool = False,
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.field(default=None, flags=["-i", "--input"]),
    #: start commit that will be included in the change log; default is the latest release
    start: yuio.git.Ref | str | None = yuio.app.field(
        default=None, flags=["-f", "--from"]
    ),
    #: end commit that will be included in the change log; default is `HEAD`
    end: yuio.git.Ref | str | None = yuio.app.field(default=None, flags=["-t", "--to"]),
    #: open generated changes for editing
    edit: bool = False,
):
    """
    generate changelog from git log.

    """

    config = _load_config(file)
    file = _locate_changelog(file, config)
    original = file.read_text()

    ctx = Context(
        file,
        original,
        config,
        _make_link_templates(file.parent, config),
    )

    repo_versions = get_repo_versions(file.parent, ctx)

    if end is None:
        end = yuio.git.Ref("HEAD")
    if start is None:
        start, _ = _find_latest_version(repo_versions, config)
        if start:
            start = f"{config.tag_prefix}{start}"
    if start:
        ref = f"{start}..{end}"
    else:
        ref = end
    yuio.io.info("Generating changelog for range `%s`", ref)

    changelog = _parse(ctx)

    _check(changelog, ctx, repo_versions)
    if ctx.has_errors() and not ignore_errors:
        ctx.report()
        ctx.exit_if_has_errors()

    repo = yuio.git.Repo(file.parent)

    groups: dict[str, list[str]] = {}
    n_messages = 0

    for trailer in repo.trailers(ref, max_entries=None):
        for key, value in trailer.trailers:
            if key.casefold() != "changelog":
                continue
            if not (match := _TRAILER_RE.match(value)):
                continue
            group = (match.group("group") or "").strip()
            message = (match.group("message") or "").strip()
            if not message:
                continue
            for (
                group_regex,
                group_candidate,
            ) in config.full_change_categories_map.items():
                if re.search(group_regex, group or message):
                    group = group_candidate
                    break
            groups.setdefault(group, []).append(message)
            n_messages += 1

    if not groups:
        yuio.io.info("No changelog messages detected in this commit range")
        return

    new_section = None
    to_remove = set()
    for i, section in _find_sections(FindMode.UNRELEASED, changelog, config):
        to_remove.add(i)
        if new_section is None:
            new_section = section
        else:
            _merge_sections(new_section, section)

    changelog.sections = [
        section for i, section in enumerate(changelog.sections) if i not in to_remove
    ]

    if new_section is None:
        new_section = Section(type=SectionType.UNRELEASED)

    additional_section = Section()
    for name, messages in groups.items():
        subsection = SubSection(type=SubSectionType.CHANGES, category=name)
        items = []
        items.append(Token("bullet_list_open", "ul", 1, markup="-", block=True))
        for message in messages:
            items.append(Token("list_item_open", "li", 1, markup="-", block=True))
            items.extend(changelog.parser.parse(message, changelog.parser_env))
            items.append(Token("list_item_close", "li", -1, markup="-", block=True))
        items.append(Token("bullet_list_close", "ul", -1, markup="-", block=True))
        subsection.content = SyntaxTreeNode(items).children
        additional_section.subsections.append(subsection)
    _merge_sections(new_section, additional_section)

    yuio.io.info(
        "Extracted `%s` changelog message%s",
        n_messages,
        "" if n_messages == 1 else "s",
    )

    if edit:
        _edit_section(changelog, ctx, new_section)

    changelog.sections.append(new_section)

    _fix(changelog, ctx, repo_versions)

    result = _render(changelog, ctx)

    if not dry_run:
        yuio.io.success("<c b>Changelog successfully updated</c>")
        file.write_text(result)
    else:
        yuio.io.success("<c b>Dry-run complete</c>")
        _print_diff(original, result, file)

    ctx.exit_if_has_errors()


class BumpMode(enum.Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    POST = "post"

    def __str__(self) -> str:
        return self.value


@main.subcommand
def bump(
    #: produce result even if errors are detected
    ignore_errors: bool = False,
    #: don't save changes, print the diff instead
    dry_run: bool = False,
    #: release version or tag that will be used for a new release
    version: BumpMode | yuio.git.Tag | str | None = yuio.app.positional(default=None),
    #: create an alpha pre-release. If `version` is given, this will bump
    #: the corresponding component and make a pre-release. If `version` is not given,
    #: the latest release must be a pre-release itself.
    alpha: bool = False,
    #: create a beta pre-release, similar to `--alpha`.
    beta: bool = False,
    #: create a release candidate, similar to `--alpha`.
    rc: bool = False,
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.field(default=None, flags=["-i", "--input"]),
    #: open generated changes for editing
    edit: bool = False,
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
    if alpha + beta + rc > 1:
        raise yuio.parse.ParsingError(
            "only one of --alpha, --beta, --rc allowed at the same time"
        )

    config = _load_config(file)
    file = _locate_changelog(file, config)
    original = file.read_text()

    ctx = Context(
        file,
        original,
        config,
        _make_link_templates(file.parent, config),
    )

    if isinstance(version, str) and version.startswith(config.tag_prefix):
        version = yuio.git.Tag(version[len(config.tag_prefix) :])

    repo_versions = None
    if isinstance(version, BumpMode) or version is None:
        repo_versions = get_repo_versions(file.parent, ctx)
        _, latest_version = _find_latest_version(repo_versions, config)
        if latest_version is None:
            raise yuio.app.AppError("No previous release to bump.")
        version = _bump_version(latest_version, version, alpha, beta, rc)
    else:
        if ctx.config.check_repo_tags:
            repo_versions = get_repo_versions(file.parent, ctx)

    parsed_version = _parse_version(version, ctx.config)
    if parsed_version is None:
        ctx.issue(
            IssueCode.INVALID_VERSION,
            "New version `%s` doesn't follow %s specification.",
            version,
            ctx.config.version_format.value,
            scope=IssueScope.EXTERNAL,
        )

    changelog = _parse(ctx)

    _check(changelog, ctx, repo_versions)
    ctx.report()
    if ctx.has_errors() and not ignore_errors:
        ctx.exit_if_has_errors()

    for _, section in _find_sections(version, changelog, config):
        if section.map is not None:
            pos = f" on line {section.map[0] + 1}"
        else:
            pos = ""
        raise yuio.app.AppError(f"release {version} already exists{pos}")

    new_section = None
    to_remove = set()
    for i, section in _find_sections(FindMode.UNRELEASED, changelog, config):
        to_remove.add(i)
        if new_section is None:
            new_section = section
        else:
            _merge_sections(new_section, section)

    changelog.sections = [
        section for i, section in enumerate(changelog.sections) if i not in to_remove
    ]

    if new_section is None:
        new_section = Section(type=SectionType.UNRELEASED)
    new_section.type = SectionType.RELEASE
    new_section.version = version
    new_section.parsed_version = parsed_version
    new_section.canonized_version = _canonize_version(parsed_version, config)
    new_section.release_date = datetime.date.today()

    if edit:
        _edit_section(changelog, ctx, new_section)

    changelog.sections.append(Section(type=SectionType.UNRELEASED))
    changelog.sections.append(new_section)

    _fix(changelog, ctx, repo_versions)

    result = _render(changelog, ctx)

    if not dry_run:
        yuio.io.success("<c b>Changelog successfully updated</c>")
        file.write_text(result)
    else:
        yuio.io.success("<c b>Dry-run complete</c>")
        _print_diff(original, result, file)

    ctx.exit_if_has_errors()


bump.usage = """
%(prog)s [<options>] <version> [-f <file>]
%(prog)s [<options>] [major|minor|patch|post] [--alpha|--beta|--rc] [-f <file>]
"""

bump.epilog = """
# examples:

## specifying version manually

you can always supply a specific version for a new release. As long as there are no
prior releases with the same version, this operation will succeed:

```sh
chk bump 1.0.5
```

## bumping a version component

you can bump a version component by setting `<version>` to `major|minor|patch|post`:

```sh
chk bump minor  # 1.0.0 -> 1.1.0
```

## pre-releases

you can make a pre-release by adding `--alpha|--beta|--rc`:

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
    json: bool = False,
    #: release version or tag, can also be `unreleased` or `latest`
    version: FindMode | yuio.git.Tag | str = yuio.app.positional(),
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.field(default=None, flags=["-i", "--input"]),
):
    """
    find a changelog entry for a given release version.

    """

    config = _load_config(file)
    file = _locate_changelog(file, config)
    original = file.read_text()

    if isinstance(version, str) and version.startswith(config.tag_prefix):
        version = version[len(config.tag_prefix) :]

    ctx = Context(
        file,
        original,
        config,
        _make_link_templates(file.parent, config),
    )

    repo_versions = None
    if ctx.config.check_repo_tags:
        repo_versions = get_repo_versions(file.parent, ctx)

    changelog = _parse(ctx)

    _check(changelog, ctx, repo_versions)
    if ctx.has_errors() and not ignore_errors:
        ctx.report()
        ctx.exit_if_has_errors()

    logger.debug("searching for %r", version)

    found = None
    for _, section in _find_sections(version, changelog, config):
        if found is None:
            found = section
        else:
            _merge_sections(found, section)

    if found is not None:
        ctx.report()
        tokens = found.to_tokens(include_heading=False)
        if json:
            data = {
                "text": _render(changelog, ctx, tokens, disable_wrapping=True),
                "version": found.version,
                "canonizedVersion": found.canonized_version,
                "tag": f"{config.tag_prefix}{found.version}" if found.version else None,
                "isUnreleased": version is FindMode.UNRELEASED,
                # "isLatest": version is FindMode.UNRELEASED,
                # "isPreRelease":
            }
        else:
            print(_render(changelog, ctx, tokens, disable_wrapping=True), end="")
    else:
        raise yuio.app.AppError("Can't find changelog entry for version `%s`", version)


find.usage = """
%(prog)s [<options>] [--json] [latest|unreleased|<version>]
"""

find.epilog = """
# examples:

find an exact version:

```sh
chk check-tag v1.0.0-rc2
```

"""


@main.subcommand
def check_tag(
    #: full name of the tag to check
    tag: yuio.git.Tag | str = yuio.app.positional(),
):
    """
    check if a git tag conforms to the versioning specification.

    This command is handy to use in release CI or in a pre-push git hook to verify
    that all tags conform to the selected versioning specification.

    """

    config = _load_config(None)
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
        raise yuio.app.AppError("Tag verification failed.")
    else:
        yuio.io.success("Tag `%s` is valid", tag)


check_tag.usage = """
%(prog)s [<options>] <tag>
"""

check_tag.epilog = """
# examples:

check if tag is valid:

```sh
chk check-tag v1.0.0-rc2
```

"""


def _load_config(file: pathlib.Path | None) -> Config:
    config = Config()
    if _GLOBAL_OPTIONS.config_path is None:
        root = file or pathlib.Path.cwd()
        while root:
            if root.joinpath(".changelog.toml").exists():
                _GLOBAL_OPTIONS.config_path = root / ".changelog.toml"
                break
            elif root.joinpath("pyproject.toml").exists():
                _GLOBAL_OPTIONS.config_path = root / "pyproject.toml"
                break
            next_root = root.parent
            if next_root == root:
                break
            root = next_root
        if _GLOBAL_OPTIONS.config_path is None:
            config.update(_GLOBAL_OPTIONS)  # type: ignore
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
            config.update(_GLOBAL_OPTIONS)  # type: ignore
            yuio.io.warning(
                "Failed to parse config file <c path>%s</c>: %s",
                _GLOBAL_OPTIONS.config_path,
                e,
            )
            logger.debug("config = %r", config)
            return config
        try:
            data = data["tool"]["changelog_keeper"]
        except KeyError as e:
            logger.debug(
                "%s doesn't have section tool.changelog_keeper",
                _GLOBAL_OPTIONS.config_path,
            )
            config.update(_GLOBAL_OPTIONS)  # type: ignore
            logger.info("using config from %s", _GLOBAL_OPTIONS.config_path)
            logger.debug("config = %r", config)
            return config

        config.update(
            Config.load_from_parsed_file(data, path=_GLOBAL_OPTIONS.config_path)
        )
    else:
        config.update(Config.load_from_toml_file(_GLOBAL_OPTIONS.config_path))

    config.update(_GLOBAL_OPTIONS)  # type: ignore
    logger.info("using config from %s", _GLOBAL_OPTIONS.config_path)
    logger.debug("config = %r", config)
    return config


def _locate_changelog(file: pathlib.Path | None, config: Config) -> pathlib.Path:
    if file is None:
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
                "in config. Alternatively, set `add_release_link` to `false`."
            )

    logger.debug("link_templates = %r", link_templates)

    _check_link_templates(link_templates)

    return link_templates


def _check_link_templates(link_templates: LinkTemplates):
    class _UsedLinkDetector:
        def __init__(self, vars: dict[str, str]) -> None:
            self._vars = vars
            self.used_keys: set[str] = set()

        def __getitem__(self, key: str) -> str:
            if key not in ["tag", "prev_tag"] and key not in self._vars:
                self.used_keys.add(key)
            return ""

    mapping = _UsedLinkDetector(link_templates.vars)
    link_templates.template.format_map(mapping)
    link_templates.template_first.format_map(mapping)
    link_templates.template_last.format_map(mapping)
    if mapping.used_keys:
        yuio.io.error(
            "Some variables used in link templates are missing "
            "from `release_link_template_vars`: `%s`. Please, add them to config.",
            ", ".join(sorted(mapping.used_keys)),
        )
        raise yuio.app.AppError("Configuration is incorrect.")


def _find_sections(version: FindMode | str, changelog: Changelog, config: Config):
    canonized_version = None
    if isinstance(version, str):
        canonized_version = (
            _canonize_version(_parse_version(version, config), config) or version
        )
    for i, section in enumerate(changelog.sections):
        if section.type == SectionType.TRIVIA:
            continue
        if section.type == SectionType.UNRELEASED:
            if version is FindMode.UNRELEASED:
                yield i, section
        logger.debug("checking release %r", section.version)
        if version is FindMode.LATEST or (
            set(filter(None, [section.version, section.canonized_version]))
            & set(filter(None, [version, canonized_version]))
        ):
            yield i, section
            if version is FindMode.LATEST:
                if section.version is not None:
                    version = section.version
                    canonized_version = section.canonized_version
                else:
                    break


def _edit_section(changelog: Changelog, ctx: Context, section: Section):
    to_edit = (
        "<!--\n"
        f" Edit changelog for release {section.version}.\n"
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


def _find_latest_version(
    changelog: Changelog, repo_versions: list[RepoVersion] | None, config: Config
) -> tuple[str | None, Version | None]:
    max_version = None
    max_version_str = None
    for section in changelog.sections:
        if section.type != SectionType.RELEASE:
            continue
        if section.parsed_version is None:
            _report_latest_version_fail("release", section.version, section.map, config)
        if max_version is None or section.parsed_version > max_version:
            max_version = section.parsed_version
            max_version_str = section.version
    if repo_versions is not None:
        for data in repo_versions:
            if data.parsed_version is None:
                _report_latest_version_fail("release", data.version, None, config)
            if max_version is None or data.parsed_version > max_version:
                max_version = data.parsed_version
                max_version_str = data.version
    return max_version_str, max_version


def _report_latest_version_fail(
    what: str, version: str | None, map: tuple[int, int] | None, config: Config
) -> _t.Never:
    if config.version_format is TagFormat.NONE:
        reason = "`version_format` is set to `none`"
        args = ()
    else:
        reason = f"{what} `%s` "
        if map:
            reason += f"on line {map[0] + 1} "
        reason += "does not follow %s specification"
        args = (version, config.version_format)
    raise yuio.app.AppError(
        "Can't determine the latest version because " + reason, *args
    )


_PY_RELEASE_NAMES = {
    "a": "an alpha release",
    "b": "a beta release",
    "rc": "a release candidate",
}


def _bump_version(
    version: Version, mode: BumpMode | None, alpha: bool, beta: bool, rc: bool
) -> str:
    if isinstance(version, packaging.version.Version):
        major, minor, patch = tuple(
            version.release[i] if len(version.release) >= i else 0 for i in range(3)
        )
        pre = version.pre
        post = version.post
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
                        "you want to do this.",
                        version,
                    )
                if post is None:
                    post = 0
                else:
                    post += 1
            case None:
                if not pre:
                    raise yuio.app.AppError(
                        "Can't create a pre-release without bumping "
                        "a primary version component: latest release `%s` "
                        "is not a pre-release.",
                        version,
                    )

        if alpha:
            if pre and pre[0] == "a":
                pre = ("a", pre[1] + 1)
            elif pre:
                raise yuio.app.AppError(
                    f"Can't create an alpha pre-release after {_PY_RELEASE_NAMES[pre[0]]}"
                )
            else:
                pre = ("a", 0)
        elif beta:
            if pre and pre[0] == "b":
                pre = ("b", pre[1] + 1)
            elif pre and pre[0] != "a":
                raise yuio.app.AppError(
                    f"Can't create a beta pre-release after {_PY_RELEASE_NAMES[pre[0]]}"
                )
            else:
                pre = ("b", 0)
        elif rc:
            if pre and pre[0] == "rc":
                pre = ("rc", pre[1] + 1)
            else:
                pre = ("rc", 0)

        if version.epoch > 0:
            prefix = f"{version.epoch}!"
        else:
            prefix = ""
        suffix = ""
        if pre:
            suffix += "".join(map(str, pre))
        if post is not None:
            suffix += f".post{post}"
        return f"{prefix}{major}.{minor}.{patch}{suffix}"
    elif isinstance(version, semver.Version):
        if alpha or beta or rc:
            raise yuio.app.AppError(
                "Semver schema doesn't support automatic pre-release bumping. "
                "Please, specify version manually."
            )
        match mode:
            case BumpMode.MAJOR:
                return str(version.bump_major())
            case BumpMode.MINOR:
                return str(version.bump_minor())
            case BumpMode.PATCH:
                return str(version.bump_patch())
            case BumpMode.POST:
                raise yuio.app.AppError(
                    "Semver schema doesn't support post versions. "
                    "Please, specify version manually."
                )
            case None:
                assert False
    else:
        assert False


class Theme(yuio.theme.DefaultTheme):
    colors = {
        "code": "bold",
        "note": [],
        "msg/text:report_error": ["red"],
        "msg/text:report_warning": ["yellow"],
        "msg/text:report_weak_warning": ["cyan"],
        "msg/text:report_info": ["cyan"],
    }


main.theme = Theme


if __name__ == "__main__":
    main.run()
