from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode

from cl_keeper.context import Context
from cl_keeper.model import (
    Changelog,
    ReleaseSection,
    RepoVersion,
    Section,
    SubSection,
    SubSectionCategoryKind,
    SubSectionType,
    UnreleasedSection,
)
from cl_keeper.sort import sorted_sections, sorted_subsections


def fix(
    changelog: Changelog, ctx: Context, repo_versions: dict[str, RepoVersion] | None
):
    changelog.sections = sorted_sections(changelog.sections)

    if (
        not changelog.sections
        or not changelog.sections[0].is_trivia()
        or not changelog.sections[0].subsections
        or not changelog.sections[0].subsections[0].content
        or changelog.sections[0].subsections[0].content[0].tag != "h1"
    ):
        changelog.sections.insert(
            0,
            Section(
                heading=None,
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
        if not isinstance(section, (ReleaseSection, UnreleasedSection)):
            continue

        if (
            ctx.config.add_release_date
            and (release := section.as_release())
            and not release.release_date
            and repo_versions is not None
            and (data := repo_versions.get(release.canonized_version))
        ):
            release.release_date = data.author_date

        if ctx.config.add_release_link:
            section.version_link, prev_tag = make_link_for_section(
                section, prev_tag, repo_versions, ctx
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
            if subsection.category_kind is SubSectionCategoryKind.KNOWN and (
                heading := ctx.config.full_change_categories[subsection.category]
            ):
                subsection.heading = format_heading(heading, 3)


def format_heading(text: str, level: int = 1):
    return SyntaxTreeNode(
        [
            Token("heading_open", f"h{level}", 1, block=True, markup="#" * level),
            Token(
                "inline",
                "",
                0,
                children=[Token("text", "", 0, content=text)],
            ),
            Token("heading_close", f"h{level}", -1, block=True),
        ],
        create_root=False,
    )


def format_section_heading_text(section: Section, ctx: Context) -> str:
    version_pre, version_post = ctx.config.version_decorations
    release_date_pre, release_date_post = ctx.config.release_date_decorations
    release_comment_pre, release_comment_post = ctx.config.release_comment_decorations

    heading = ""

    if section.is_unreleased():
        heading += ctx.config.unreleased_decorations[0]
        heading += ctx.config.unreleased_name
        heading += ctx.config.unreleased_decorations[1]
    elif release := section.as_release():
        heading += ctx.config.release_decorations[0]
        heading += f"{version_pre}{release.version}{version_post}"
        if ctx.config.add_release_date:
            if release.release_date:
                release_date = release.release_date.isoformat()
            else:
                release_date = release.release_date_fmt
            if release_date is not None:
                heading += f"{release_date_pre}{release_date}{release_date_post}"
        if release.release_comment:
            heading += (
                f"{release_comment_pre}{release.release_comment}{release_comment_post}"
            )
        heading += ctx.config.release_decorations[1]

    return heading


def format_section_heading(section: Section, ctx: Context) -> SyntaxTreeNode:
    version_pre, version_post = ctx.config.version_decorations
    release_date_pre, release_date_post = ctx.config.release_date_decorations
    release_comment_pre, release_comment_post = ctx.config.release_comment_decorations

    inline: list[Token] = []

    if unreleased := section.as_unreleased():
        if ctx.config.unreleased_decorations[0]:
            inline.append(
                Token("text", "", 0, content=ctx.config.unreleased_decorations[0])
            )
        if unreleased.version_link and ctx.config.add_release_link:
            inline.append(
                Token(
                    "link_open",
                    "a",
                    1,
                    attrs={"href": unreleased.version_link},
                    meta={"label": unreleased.version_label},
                )
            )
        inline.append(Token("text", "", 0, content=ctx.config.unreleased_name))
        if unreleased.version_link and ctx.config.add_release_link:
            inline.append(Token("link_close", "a", -1))
        if ctx.config.unreleased_decorations[1]:
            inline.append(
                Token("text", "", 0, content=ctx.config.unreleased_decorations[1])
            )
    elif release := section.as_release():
        if ctx.config.release_decorations[0]:
            inline.append(
                Token("text", "", 0, content=ctx.config.release_decorations[0])
            )

        if release.version_link and ctx.config.add_release_link:
            inline.append(
                Token(
                    "link_open",
                    "a",
                    1,
                    attrs={"href": release.version_link},
                    meta={"label": release.version_label},
                )
            )
        inline.append(
            Token(
                "text", "", 0, content=f"{version_pre}{release.version}{version_post}"
            )
        )
        if release.version_link and ctx.config.add_release_link:
            inline.append(Token("link_close", "a", -1))

        if ctx.config.add_release_date:
            if release.release_date:
                release_date = release.release_date.isoformat()
            else:
                release_date = release.release_date_fmt
            if release_date is not None:
                inline.append(
                    Token(
                        "text",
                        "",
                        0,
                        content=f"{release_date_pre}{release_date}{release_date_post}",
                    )
                )
        if release.release_comment:
            inline.append(
                Token(
                    "text",
                    "",
                    0,
                    content=f"{release_comment_pre}{release.release_comment}{release_comment_post}",
                )
            )

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
    if section.is_unreleased():
        return ctx.config.unreleased_name
    elif release := section.as_release():
        pre, post = ctx.config.version_decorations
        return f"{pre}{release.version}{post}"
    else:
        return None


def make_link_for_section(
    section: Section,
    prev_tag: str | None,
    repo_versions: dict[str, RepoVersion] | None,
    ctx: Context,
):
    if section.is_unreleased():
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
    elif release := section.as_release():
        if repo_versions is not None and (
            data := repo_versions.get(release.canonized_version)
        ):
            tag = f"{ctx.config.tag_prefix}{data.version}"
        else:
            tag = f"{ctx.config.tag_prefix}{release.version}"
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
    else:
        return None, None
