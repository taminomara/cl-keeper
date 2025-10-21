import datetime
import re
import typing as _t

import mdformat.plugins
import packaging.version
import semver
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdformat.renderer import MDRenderer

from cl_keeper.config import Config, VersionFormat
from cl_keeper.context import Context, IssueCode
from cl_keeper.fix import format_section_heading_text
from cl_keeper.model import (
    Changelog,
    ReleaseSection,
    Section,
    SubSection,
    SubSectionCategoryKind,
    SubSectionType,
    UnreleasedSection,
    Version,
)

_VERSION_RE = re.compile(
    r"""
        (?:
            (?:\d+!)?
            \d+\.\d+\.\d+
            (?:[+-._]?[0-9a-zA-Z-+.]*)?
        )
    """,
    re.VERBOSE | re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"""
        (?P<year>\d\d\d\d)
        -
        (?P<month>\d\d)
        -
        (?P<day>\d\d)
    """,
    re.VERBOSE,
)


def parse(ctx: Context) -> Changelog:
    """
    Parse a changelog.

    """

    parser = build_parser()
    parser_env = {"references": {}}

    tokens = parser.parse(ctx.src, parser_env)
    root = SyntaxTreeNode(tokens)

    sections = build_changelog(root, ctx)

    return Changelog(
        sections=sections,
        parser=parser,
        parser_env=parser_env,
    )


def build_parser() -> MarkdownIt:
    parser = MarkdownIt(renderer_cls=MDRenderer)  # pyright: ignore[reportArgumentType]
    parser.options["store_labels"] = True
    parser.options["parser_extension"] = []
    parser.options["mdformat"] = {}
    for name in ["footnote", "frontmatter", "tables", "gfm_alerts", "gfm"]:
        plugin = mdformat.plugins.PARSER_EXTENSIONS[name]
        if plugin not in parser.options["parser_extension"]:
            parser.options["parser_extension"].append(plugin)
            plugin.update_mdit(parser)

    return parser


def build_changelog(root: SyntaxTreeNode, ctx: Context) -> list[Section]:
    """
    Build changelog sections from content.

    """

    sections: list[Section] = []
    for heading, content in split_into_sections(root.children, 2):
        subsections: list[SubSection] = []
        if not heading:
            subsections.append(SubSection(content=content))
        else:
            for subheading, content in split_into_sections(content, 3):
                subsection = SubSection(heading=subheading, content=content)
                detect_subsection_metadata(subsection, ctx)
                subsections.append(subsection)
        sections.append(create_section(heading, subsections, ctx))
    return sections


def split_into_sections(nodes: _t.Iterable[SyntaxTreeNode], target_heading_level: int):
    """
    Group nodes into sections, splitting them at heading of the given level.

    """

    sections: list[tuple[SyntaxTreeNode | None, list[SyntaxTreeNode]]] = []

    current_heading: SyntaxTreeNode | None = None
    current_section: list[SyntaxTreeNode] = []

    for node in nodes:
        if node.type != "heading":
            current_section.append(node)
            continue
        level = int(node.tag[1:])
        if level > target_heading_level:
            current_section.append(node)
            continue
        else:
            if current_heading or current_section:
                sections.append((current_heading, current_section))
            if level == target_heading_level:
                current_heading = node
                current_section = []
            else:
                current_heading = None
                current_section = [node]
    if current_heading or current_section:
        sections.append((current_heading, current_section))
    return sections


def create_section(
    heading: SyntaxTreeNode | None, subsections: list[SubSection], ctx: Context
) -> Section:
    """
    Scan section heading and set its type, version, release date, and so on.

    """

    heading_text = _node_to_text(heading)

    if heading is None or heading.tag != "h2" or heading_text is None:
        return Section(
            heading=heading,
            subsections=subsections,
        )

    link: str | None = None
    label: str | None = None
    for node in heading.walk():
        if node.type == "link":
            link = str(node.attrs.get("href", "")) or None
            label = node.meta.get("label")
            break

    if re.search(ctx.config.unreleased_pattern, heading_text):
        section = UnreleasedSection(
            heading=heading,
            subsections=subsections,
            version_link=link,
            version_label=label,
        )

        canonical_heading = format_section_heading_text(section, ctx)
        if heading_text != canonical_heading:
            ctx.issue(
                IssueCode.UNRELEASED_HEADING_FORMAT,
                "Heading for unreleased changes isn't properly formatted, should be `%s`",
                canonical_heading,
                pos=section.heading,
            )

        return section

    version_match = _VERSION_RE.search(heading_text)
    if not version_match:
        section = Section(
            heading=heading,
            subsections=subsections,
        )

        ctx.issue(
            IssueCode.GENERAL_FORMATTING_ERROR,
            "Changelog section doesn't contain a release version",
            pos=section.heading,
        )

        return section

    version = version_match.group(0)

    parsed_version = parse_version(version, ctx.config)
    if parsed_version is None and ctx.config.version_format is not VersionFormat.NONE:
        ctx.issue(
            IssueCode.INVALID_VERSION,
            "Version `%s` doesn't follow %s specification",
            version,
            ctx.config.version_format.value,
            pos=heading,
        )
    canonized_version = canonize_version(parsed_version, ctx.config) or version

    date_match = _DATE_RE.search(heading_text)
    if date_match is None:
        release_date = None
        release_date_fmt = None
    else:
        release_date_fmt = date_match.group()
        try:
            release_date = datetime.date(
                year=int(date_match.group("year")),
                month=int(date_match.group("month")),
                day=int(date_match.group("day")),
            )
        except ValueError as e:
            release_date = None
            ctx.issue(
                IssueCode.INVALID_RELEASE_DATE,
                "Incorrect release date `%s`: %s",
                release_date_fmt,
                e,
                pos=heading,
            )

    found_unresolved_link = False
    if date_match is None:
        prefix = heading_text[: version_match.start()]
        suffix = heading_text[version_match.end() :]

        prefix = prefix.removesuffix(ctx.config.version_decorations[0])
        suffix = suffix.removeprefix(ctx.config.version_decorations[1])

        if check_broken_link(prefix, suffix):
            ctx.issue(
                IssueCode.RELEASE_HEADING_FORMAT,
                "Can't resolve version's link",
                pos=heading,
            )
            suffix = suffix.lstrip().removeprefix("]")
            found_unresolved_link = True
    elif version_match.end() <= date_match.start():
        prefix = heading_text[: version_match.start()]
        middle = heading_text[version_match.end() : date_match.start()]
        suffix = heading_text[date_match.end() :]

        prefix = prefix.removesuffix(ctx.config.version_decorations[0])
        middle = middle.removeprefix(ctx.config.version_decorations[1])
        suffix = suffix.removeprefix(ctx.config.release_date_decorations[1])

        if check_broken_link(prefix, middle):
            ctx.issue(
                IssueCode.RELEASE_HEADING_FORMAT,
                "Can't resolve version's link",
                pos=heading,
            )
            found_unresolved_link = True

        if middle.endswith(("(", "[", "<", "{")) and suffix.startswith(
            (")", "]", ">", "}")
        ):
            suffix = suffix[1:]
    else:
        prefix = heading_text[: date_match.start()]
        middle = heading_text[date_match.end() : version_match.start()]
        suffix = heading_text[version_match.end() :]

        middle = middle.removesuffix(ctx.config.version_decorations[0])
        suffix = suffix.removeprefix(ctx.config.version_decorations[1])

        if check_broken_link(middle, suffix):
            ctx.issue(
                IssueCode.RELEASE_HEADING_FORMAT,
                "Can't resolve version's link",
                pos=heading,
            )
            suffix = suffix.lstrip().removeprefix("]")
            found_unresolved_link = True

        if middle.endswith(("(", "[", "<", "{")) and suffix.startswith(
            (")", "]", ">", "}")
        ):
            suffix = suffix[1:]

    release_comment = (
        suffix.removeprefix(ctx.config.release_comment_decorations[0])
        .removesuffix(ctx.config.release_comment_decorations[1])
        .strip()
    )

    section = ReleaseSection(
        heading=heading,
        subsections=subsections,
        version=version,
        parsed_version=parsed_version,
        canonized_version=canonized_version,
        version_link=link,
        version_label=label,
        release_date=release_date,
        release_date_fmt=release_date_fmt,
        release_comment=release_comment,
    )

    if not found_unresolved_link:
        canonical_heading = format_section_heading_text(section, ctx)
        if canonical_heading != heading_text:
            ctx.issue(
                IssueCode.RELEASE_HEADING_FORMAT,
                "Heading for release `%s` isn't properly formatted, should be `%s`",
                section.version,
                canonical_heading,
                pos=section.heading,
            )

    return section


def check_broken_link(prefix: str, suffix: str):
    return prefix.rstrip().endswith("[") and suffix.lstrip().startswith("]")


def detect_subsection_metadata(subsection: SubSection, ctx: Context):
    """
    Scan subsection heading and set its type, category, and sort key.

    """

    heading = _node_to_text(subsection.heading)

    if subsection.heading is None or subsection.heading.tag != "h3" or heading is None:
        subsection.type = SubSectionType.TRIVIA
        subsection.category_kind = SubSectionCategoryKind.UNKNOWN
        subsection.category = ""
        subsection.sort_key = None
        return

    for regex, category in ctx.config.full_change_categories_map.items():
        if re.search(regex, heading):
            subsection.type = SubSectionType.CHANGES
            subsection.category_kind = SubSectionCategoryKind.KNOWN
            subsection.category = category
            subsection.sort_key = ctx.config.change_categories_sort_keys.get(category)

            canonical_heading = ctx.config.full_change_categories.get(category)
            if canonical_heading and canonical_heading != heading:
                ctx.issue(
                    IssueCode.CHANGE_CATEGORY_HEADING_FORMAT,
                    "Heading for change group isn't properly formatted, should be `%s`",
                    canonical_heading,
                    pos=subsection.heading,
                )

            return

    # A group with h3-level heading is always a change category,
    # albeit not a recognized one.
    subsection.type = SubSectionType.CHANGES
    subsection.category_kind = SubSectionCategoryKind.UNKNOWN
    subsection.category = heading.casefold()
    subsection.sort_key = None

    ctx.issue(
        IssueCode.UNKNOWN_CHANGE_CATEGORY,
        "Unknown change group `%s`",
        heading,
        pos=subsection.heading,
    )


def _node_to_text(heading: SyntaxTreeNode | None):
    if heading is None:
        return None
    text = ""
    for node in heading.walk(include_self=False):
        if node.type == "text":
            text += node.content
    return text.strip()


_STRICT_SEMVER_TEMPLATE = re.compile(
    r"""
        ^
        (?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)
        (?:-(?:alpha|beta|rc)(?:0|[1-9]\d*))?
        $
    """,
    re.VERBOSE,
)

_PYTHON_SEMVER_TEMPLATE = re.compile(
    r"""
        ^
        (?:(?:0|[1-9]\d*)!)?
        (?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)
        (?:
            -(?:
                (?:alpha|beta|rc)(?:0|[1-9]\d*)(?:\.post(?:0|[1-9]\d*))?
                | (?:post(?:0|[1-9]\d*))
            )
        )?
        $
    """,
    re.VERBOSE,
)

_STRICT_PYTHON_TEMPLATE = re.compile(
    r"""
        ^
        (?:(?:0|[1-9]\d*)!)?
        (?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)
        (?:(?:a|b|rc)(?:0|[1-9]\d*))?
        (?:\.post(?:0|[1-9]\d*))?
        $
    """,
    re.VERBOSE,
)


def parse_version(version: str | None, config: Config) -> Version | None:
    if version is None:
        return None
    try:
        match config.version_format:
            case VersionFormat.SEMVER:
                return _t.cast(Version, semver.Version.parse(version))
            case VersionFormat.SEMVER_STRICT:
                if not _STRICT_SEMVER_TEMPLATE.match(version):
                    return None
                return _t.cast(Version, semver.Version.parse(version))
            case VersionFormat.PYTHON:
                return _t.cast(Version, packaging.version.Version(version))
            case VersionFormat.PYTHON_STRICT:
                if not _STRICT_PYTHON_TEMPLATE.match(version):
                    return None
                return _t.cast(Version, packaging.version.Version(version))
            case VersionFormat.PYTHON_SEMVER:
                if not _PYTHON_SEMVER_TEMPLATE.match(version):
                    return None
                return _t.cast(Version, packaging.version.Version(version))
            case VersionFormat.NONE:
                return None
    except ValueError:
        return None


def canonize_version(version: Version | None, config: Config) -> str | None:
    if version is None:
        return None
    match config.version_format:
        case VersionFormat.SEMVER:
            assert isinstance(version, semver.Version)
            return str(version)
        case VersionFormat.SEMVER_STRICT:
            assert isinstance(version, semver.Version)
            return str(version)
        case VersionFormat.PYTHON:
            assert isinstance(version, packaging.version.Version)
            return str(version)
        case VersionFormat.PYTHON_STRICT:
            assert isinstance(version, packaging.version.Version)
            return str(version)
        case VersionFormat.PYTHON_SEMVER:
            assert isinstance(version, packaging.version.Version)

            parts = []

            # Epoch
            if version.epoch != 0:
                parts.append(f"{version.epoch}!")

            # Release segment
            assert len(version.release) <= 3
            parts.append(
                ".".join(
                    str(version.release[i] if len(version.release) >= i else 0)
                    for i in range(3)
                )
            )

            # Pre-release
            if version.pre is not None:
                match version.pre[0]:
                    case "a":
                        parts.append("-alpha")
                        parts.append(str(version.pre[1]))
                    case "b":
                        parts.append("-beta")
                        parts.append(str(version.pre[1]))
                    case "rc":
                        parts.append("-rc")
                        parts.append(str(version.pre[1]))
                    case _:
                        assert False

            # Post-release
            if version.post is not None:
                if version.pre is not None:
                    parts.append(".post")
                else:
                    parts.append("-post")
                parts.append(str(version.post))

            # Development release
            assert version.dev is None

            # Local version segment
            assert version.local is None

            return "".join(parts)
        case VersionFormat.NONE:
            return None
