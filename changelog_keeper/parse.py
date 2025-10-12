import datetime
import re
import typing as _t

import mdformat.plugins
import packaging.version
import semver
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdformat.renderer import MDRenderer

from changelog_keeper.config import TagFormat
from changelog_keeper.context import Context, IssueSeverity
from changelog_keeper.fix import format_section_heading_text
from changelog_keeper.model import (
    Changelog,
    Section,
    SectionType,
    SubSection,
    SubSectionCategoryKind,
    SubSectionType,
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
        section = Section(heading=heading, subsections=subsections)
        detect_section_metadata(section, ctx)
        sections.append(section)
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


def detect_section_metadata(section: Section, ctx: Context):
    """
    Scan section heading and set its type, version, release date, and so on.

    """

    heading = _node_to_text(section.heading)

    if section.heading is None or section.heading.tag != "h2" or heading is None:
        section.type = SectionType.TRIVIA
        section.version = None
        section.parsed_version = None
        section.version_link = None
        section.version_label = None
        section.release_date = None
        section.release_comment = None
        return

    link: str | None = None
    label: str | None = None
    for node in section.heading.walk():
        if node.type == "link":
            link = str(node.attrs.get("href", "")) or None
            label = node.meta.get("label")
            break

    if re.search(ctx.config.unreleased_pattern, heading):
        section.type = SectionType.UNRELEASED
        section.version = None
        section.parsed_version = None
        section.version_link = link
        section.version_label = label
        section.release_date = None
        section.release_comment = None

        canonical_heading = format_section_heading_text(section, ctx)
        if heading != canonical_heading:
            ctx.issue(
                "Heading for unreleased changes isn't properly formatted, should be `%s`.",
                canonical_heading,
                pos=section.heading,
            )

        return

    version_match = _VERSION_RE.search(heading)
    if not version_match:
        section.type = SectionType.TRIVIA
        section.version = None
        section.parsed_version = None
        section.version_link = link
        section.version_label = label
        section.release_date = None
        section.release_date_fmt = None
        section.release_comment = None

        ctx.issue(
            "Changelog section doesn't contain a release version.",
            pos=section.heading,
        )

        return

    section.type = SectionType.RELEASE
    section.version = version_match.group(0)
    section.version_link = link
    section.version_label = label

    section.parsed_version = parse_version(section.version, ctx)
    if section.parsed_version is None:
        ctx.issue(
            "Version `%s` doesn't follow %s specification.",
            section.version,
            ctx.config.version_format.value,
            pos=section.heading,
            severity=IssueSeverity.CRITICAL,
        )

    date_match = _DATE_RE.search(heading)
    if date_match is None:
        section.release_date = None
        section.release_date_fmt = None
    else:
        section.release_date_fmt = date_match.group()
        try:
            section.release_date = datetime.date(
                year=int(date_match.group("year")),
                month=int(date_match.group("month")),
                day=int(date_match.group("day")),
            )
        except ValueError as e:
            section.release_date = None
            ctx.issue(
                "Incorrect release date `%s`: %s.",
                section.release_date_fmt,
                e,
                pos=section.heading,
            )

    found_unresolved_link = False
    if date_match is None:
        prefix = heading[: version_match.start()]
        suffix = heading[version_match.end() :]

        prefix = prefix.removesuffix(ctx.config.version_decorations[0])
        suffix = suffix.removeprefix(ctx.config.version_decorations[1])

        if check_broken_link(prefix, suffix):
            ctx.issue("Can't resolve version's link.", pos=section.heading)
            suffix = suffix.lstrip().removeprefix("]")
            found_unresolved_link = True
    elif version_match.end() <= date_match.start():
        prefix = heading[: version_match.start()]
        middle = heading[version_match.end() : date_match.start()]
        suffix = heading[date_match.end() :]

        prefix = prefix.removesuffix(ctx.config.version_decorations[0])
        middle = middle.removeprefix(ctx.config.version_decorations[1])
        suffix = suffix.removeprefix(ctx.config.release_date_decorations[1])

        if check_broken_link(prefix, middle):
            ctx.issue("Can't resolve version's link.", pos=section.heading)
            found_unresolved_link = True

        if middle.endswith("("):
            suffix = suffix.removeprefix(")")
    else:
        prefix = heading[: date_match.start()]
        middle = heading[date_match.end() : version_match.start()]
        suffix = heading[version_match.end() :]

        middle = middle.removesuffix(ctx.config.version_decorations[0])
        suffix = suffix.removeprefix(ctx.config.version_decorations[1])

        if check_broken_link(middle, suffix):
            ctx.issue("Can't resolve version's link.", pos=section.heading)
            suffix = suffix.lstrip().removeprefix("]")
            found_unresolved_link = True

        if middle.endswith("("):
            suffix = suffix.removeprefix(")")

    section.release_comment = (
        suffix.removeprefix(ctx.config.release_comment_decorations[0])
        .removesuffix(ctx.config.release_comment_decorations[1])
        .strip()
    )

    if not found_unresolved_link:
        canonical_heading = format_section_heading_text(section, ctx)
        if canonical_heading != heading:
            ctx.issue(
                "Heading for release `%s` isn't properly formatted, should be `%s`.",
                section.version,
                canonical_heading,
                pos=section.heading,
            )


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

            canonical_heading = ctx.config.change_categories.get(category)
            if canonical_heading and canonical_heading != heading:
                ctx.issue(
                    "Heading for change group isn't properly formatted, should be `%s`.",
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

    if not ctx.config.allow_unknown_change_categories:
        ctx.issue("Unknown change group `%s`", heading, pos=subsection.heading)


def _node_to_text(heading: SyntaxTreeNode | None):
    if heading is None:
        return None
    text = ""
    for node in heading.walk(include_self=False):
        if node.type == "text":
            text += node.content
    return text.strip()


def parse_version(version: str | None, ctx: Context) -> Version | None:
    if version is None:
        return None
    try:
        match ctx.config.version_format:
            case TagFormat.SEMVER:
                return _t.cast(Version, semver.Version.parse(version))
            case TagFormat.PYTHON:
                return _t.cast(Version, packaging.version.Version(version))
    except ValueError:
        return None
