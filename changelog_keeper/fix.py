import yuio.git
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode

from changelog_keeper.context import Context
from changelog_keeper.model import (
    Changelog,
    Section,
    SectionType,
    SubSection,
    SubSectionCategoryKind,
    SubSectionType,
)
from changelog_keeper.sort import sorted_sections, sorted_subsections


def fix(
    changelog: Changelog, ctx: Context, repo_versions: dict[str, yuio.git.Commit] | None
):
    if repo_versions:
        from changelog_keeper.parse import parse_version

        known_tags = set(repo_versions)
        releases = set(
            section.version for section in changelog.sections if section.version
        )
        for missed_version in known_tags - releases:
            changelog.sections.append(
                Section(
                    type=SectionType.RELEASE,
                    version=missed_version,
                    parsed_version=parse_version(missed_version, ctx),
                    release_date=repo_versions[missed_version].author_datetime.date(),
                )
            )

    changelog.sections = sorted_sections(changelog.sections)

    if (
        not changelog.sections
        or changelog.sections[0].type != SectionType.TRIVIA
        or not changelog.sections[0].subsections
        or not changelog.sections[0].subsections[0].content
        or changelog.sections[0].subsections[0].content[0].tag != "h1"
    ):
        changelog.sections.insert(
            0,
            Section(
                type=SectionType.TRIVIA,
                subsections=[
                    SubSection(
                        type=SubSectionType.TRIVIA,
                        content=[format_heading("Changelog")],
                    )
                ],
            ),
        )

    prev_tag: str | None = None
    for section in reversed(changelog.sections):
        if section.type == SectionType.TRIVIA:
            continue

        if (
            ctx.config.add_release_date
            and not section.release_date
            and repo_versions
            and (commit := repo_versions.get(section.version or ""))
        ):
            section.release_date = commit.author_datetime.date()

        if ctx.config.add_release_link:
            section.version_link, prev_tag = make_link_for_section(
                section, prev_tag, ctx
            )
            section.version_label = format_section_label(section, ctx)
            if section.version_label:
                changelog.parser_env["references"][section.version_label] = {
                    "title": "",
                    "href": section.version_link,
                    "map": None,
                }

        section.heading = format_section_heading(section, ctx)

        section.subsections = sorted_subsections(section.subsections)
        for subsection in reversed(section.subsections):
            if subsection.category_kind is SubSectionCategoryKind.KNOWN:
                subsection.heading = format_heading(
                    ctx.config.full_change_categories[subsection.category]
                )


def format_heading(text: str):
    return SyntaxTreeNode(
        [
            Token("heading_open", "h1", 1, block=True, markup="#"),
            Token(
                "inline",
                "",
                0,
                children=[Token("text", "", 0, content=text)],
            ),
            Token("heading_close", "h1", -1, block=True),
        ],
        create_root=False,
    )


def format_section_heading_text(section: Section, ctx: Context) -> str:
    version_pre, version_post = ctx.config.version_decorations
    release_date_pre, release_date_post = ctx.config.release_date_decorations
    release_comment_pre, release_comment_post = ctx.config.release_comment_decorations

    heading = ""

    if section.type is SectionType.UNRELEASED:
        heading += ctx.config.unreleased_decorations[0]
    else:
        heading += ctx.config.release_decorations[0]

    if section.type is SectionType.UNRELEASED:
        heading += ctx.config.unreleased_name
    else:
        heading += f"{version_pre}{section.version}{version_post}"

    if ctx.config.add_release_date:
        if section.release_date:
            release_date = section.release_date.isoformat()
        else:
            release_date = section.release_date_fmt
        if release_date is not None:
            heading += f"{release_date_pre}{release_date}{release_date_post}"

    if section.release_comment:
        heading += (
            f"{release_comment_pre}{section.release_comment}{release_comment_post}"
        )

    if section.type is SectionType.UNRELEASED:
        heading += ctx.config.unreleased_decorations[1]
    else:
        heading += ctx.config.release_decorations[1]

    return heading


def format_section_heading(section: Section, ctx: Context) -> SyntaxTreeNode:
    version_pre, version_post = ctx.config.version_decorations
    release_date_pre, release_date_post = ctx.config.release_date_decorations
    release_comment_pre, release_comment_post = ctx.config.release_comment_decorations

    inline: list[Token] = []

    if section.type is SectionType.UNRELEASED:
        if ctx.config.unreleased_decorations[0]:
            inline.append(
                Token("text", "", 0, content=ctx.config.unreleased_decorations[0])
            )
    else:
        if ctx.config.release_decorations[0]:
            inline.append(
                Token("text", "", 0, content=ctx.config.release_decorations[0])
            )

    if section.version_link and ctx.config.add_release_link:
        inline.append(
            Token(
                "link_open",
                "a",
                1,
                attrs={"href": section.version_link},
                meta={"label": section.version_label},
            )
        )

    if section.type is SectionType.UNRELEASED:
        inline.append(Token("text", "", 0, content=ctx.config.unreleased_name))
    else:
        inline.append(
            Token(
                "text", "", 0, content=f"{version_pre}{section.version}{version_post}"
            )
        )

    if section.version_link and ctx.config.add_release_link:
        inline.append(Token("link_close", "a", -1))

    if ctx.config.add_release_date:
        if section.release_date:
            release_date = section.release_date.isoformat()
        else:
            release_date = section.release_date_fmt
        if release_date is not None:
            inline.append(
                Token(
                    "text",
                    "",
                    0,
                    content=f"{release_date_pre}{release_date}{release_date_post}",
                )
            )

    if section.release_comment:
        inline.append(
            Token(
                "text",
                "",
                0,
                content=f"{release_comment_pre}{section.release_comment}{release_comment_post}",
            )
        )

    if section.type is SectionType.UNRELEASED:
        if ctx.config.unreleased_decorations[1]:
            inline.append(
                Token("text", "", 0, content=ctx.config.unreleased_decorations[1])
            )
    else:
        if ctx.config.release_decorations[1]:
            inline.append(
                Token("text", "", 0, content=ctx.config.release_decorations[1])
            )

    return SyntaxTreeNode(
        [
            Token("heading_open", "h2", 1, block=True, markup="##"),
            Token("inline", "", 0, children=inline),
            Token("heading_close", "h2", -1, block=True),
        ],
        create_root=False,
    )


def format_section_label(section: Section, ctx: Context):
    if section.type is SectionType.UNRELEASED:
        return ctx.config.unreleased_name
    else:
        pre, post = ctx.config.version_decorations
        return f"{pre}{section.version}{post}"


def make_link_for_section(
    section: Section,
    prev_tag: str | None,
    ctx: Context,
):
    if section.type is SectionType.UNRELEASED:
        if prev_tag is not None:
            return (
                ctx.link_templates.template_last.format(
                    **ctx.link_templates.vars,
                    prev_tag=prev_tag,
                ),
                prev_tag,
            )
        else:
            return None, None

    tag = f"{ctx.config.tag_prefix}{section.version}"
    if prev_tag:
        return (
            ctx.link_templates.template.format(
                **ctx.link_templates.vars,
                tag=tag,
                prev_tag=prev_tag,
            ),
            tag,
        )
    else:
        return (
            ctx.link_templates.template_first.format(
                **ctx.link_templates.vars, tag=tag
            ),
            tag,
        )
