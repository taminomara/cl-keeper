import datetime
import enum
import logging
import pathlib
import re
import tomllib

import yuio.app
import yuio.git
import yuio.io
import yuio.theme
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode

from changelog_keeper._version import __version__
from changelog_keeper.check import check as _check
from changelog_keeper.config import PYTHON_PRESET, Config, GlobalConfig, LinkTemplates
from changelog_keeper.context import Context, IssueScope, IssueSeverity
from changelog_keeper.fix import fix as _fix
from changelog_keeper.model import (
    Changelog,
    Section,
    SectionType,
    SubSection,
    SubSectionType,
)
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
%(prog)s [--config <*.toml>] [--strict|--stricter] [-v] <subcommand>
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
    file: pathlib.Path | None = yuio.app.positional(default=None),
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
    file: pathlib.Path | None = yuio.app.positional(default=None),
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
    file: pathlib.Path | None = yuio.app.positional(default=None),
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
        max_version = None
        start = ""
        for version in repo_versions:
            parsed_version = _parse_version(version, ctx)
            assert parsed_version
            if max_version is None:
                max_version = parsed_version
                start = f"{config.tag_prefix}{version}"
            elif max_version < parsed_version:
                max_version = parsed_version
                start = f"{config.tag_prefix}{version}"

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
    for i, section in _find_sections(FindMode.UNRELEASED, changelog):
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


@main.subcommand
def bump(
    #: produce result even if errors are detected
    ignore_errors: bool = False,
    #: don't save changes, print the diff instead
    dry_run: bool = False,
    #: release version or tag that will be used for a new release
    version: yuio.git.Tag | str = yuio.app.positional(),
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.positional(default=None),
    #: open generated changes for editing
    edit: bool = False,
):
    """
    move entries from `unreleased` to a new release.

    """

    config = _load_config(file)
    file = _locate_changelog(file, config)
    original = file.read_text()

    if version.startswith(config.tag_prefix):
        version = version[len(config.tag_prefix) :]

    ctx = Context(
        file,
        original,
        config,
        _make_link_templates(file.parent, config),
    )

    repo_versions = None
    if ctx.config.check_repo_tags and config.strictness:
        repo_versions = get_repo_versions(file.parent, ctx)

    changelog = _parse(ctx)

    _check(changelog, ctx, repo_versions)

    parsed_version = _parse_version(version, ctx)
    if parsed_version is None:
        ctx.issue(
            "New version `%s` doesn't follow %s specification.",
            version,
            ctx.config.version_format.value,
            scope=IssueScope.EXTERNAL,
            severity=IssueSeverity.CRITICAL,
        )
    if ctx.has_errors() and not ignore_errors:
        ctx.report()
        ctx.exit_if_has_errors()

    for _, section in _find_sections(version, changelog):
        if section.map is not None:
            pos = f" on line {section.map[0] + 2}"
        else:
            pos = ""
        raise yuio.app.AppError(f"release {version} already exists{pos}")

    new_section = None
    to_remove = set()
    for i, section in _find_sections(FindMode.UNRELEASED, changelog):
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


class FindMode(enum.Enum):
    LATEST = "latest"
    UNRELEASED = "unreleased"

    def __str__(self) -> str:
        return self.value


@main.subcommand
def find(
    #: produce result even if errors are detected
    ignore_errors: bool = False,
    #: release version or tag, can also be `unreleased` or `latest`
    version: FindMode | yuio.git.Tag | str = yuio.app.positional(),
    #: path to the changelog file
    file: pathlib.Path | None = yuio.app.positional(default=None),
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
    if ctx.config.check_repo_tags and config.strictness:
        repo_versions = get_repo_versions(file.parent, ctx)

    changelog = _parse(ctx)

    _check(changelog, ctx, repo_versions)
    if ctx.has_errors() and not ignore_errors:
        ctx.report()
        ctx.exit_if_has_errors()

    logger.debug("searching for %r", version)

    found = None
    for _, section in _find_sections(version, changelog):
        if found is None:
            found = section
        else:
            _merge_sections(found, section)

    if found is not None:
        ctx.report()
        tokens = found.to_tokens(include_heading=False)
        print(_render(changelog, ctx, tokens, disable_wrapping=True), end="")
    else:
        raise yuio.app.AppError("Can't find changelog entry for version `%s`", version)


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


def _find_sections(version: FindMode | str, changelog: Changelog):
    if isinstance(version, str):
        version = version.casefold()
    for i, section in enumerate(changelog.sections):
        if section.type == SectionType.TRIVIA:
            continue
        if section.type == SectionType.UNRELEASED:
            if version is FindMode.UNRELEASED:
                yield i, section
        logger.debug("checking release %r", section.version)
        if version is FindMode.LATEST or (
            section.version is not None and section.version.casefold() == version
        ):
            yield i, section
            if version is FindMode.LATEST:
                if section.version is not None:
                    version = section.version
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


class Theme(yuio.theme.DefaultTheme):
    colors = {
        "msg/text:report_error": ["red"],
        "msg/text:report_warning": ["yellow"],
        "msg/text:report_weak_warning": ["cyan"],
        "msg/text:report_info": ["cyan"],
    }


main.theme = Theme


if __name__ == "__main__":
    main.run()
