from __future__ import annotations

import typing as _t

import yuio.git

from changelog_keeper.context import Context, IssueScope, IssueSeverity
from changelog_keeper.fix import make_link_for_section
from changelog_keeper.model import (
    Changelog,
    Section,
    SectionType,
    SubSection,
    SubSectionType,
)


def check(
    changelog: Changelog, ctx: Context, repo_versions: dict[str, yuio.git.Commit] | None
):
    check_duplicates(changelog.sections, ctx)
    found_unordered_sections = check_order(changelog.sections, ctx)
    check_links(
        changelog.sections,
        ctx,
        not found_unordered_sections,
    )
    check_dates(changelog.sections, ctx, repo_versions)
    check_section_content(changelog.sections, ctx)
    if repo_versions is not None:
        check_tags(changelog.sections, ctx, repo_versions)


def check_duplicates(sections: _t.Iterable[Section], ctx: Context):
    seen_unreleased = False
    seen_versions: set[str] = set()

    for section in sections:
        match section.type:
            case SectionType.TRIVIA:
                continue
            case SectionType.UNRELEASED:
                if seen_unreleased:
                    ctx.issue(
                        "Found multiple sections for unreleased changes.", pos=section
                    )
                seen_unreleased = True
            case SectionType.RELEASE:
                if section.version in seen_versions:
                    ctx.issue(
                        "Found multiple sections for release `%s`.",
                        section.version,
                        pos=section,
                    )
                if section.version:
                    seen_versions.add(section.version)
        check_duplicates_in_subsections(section.subsections, section.version, ctx)


def check_duplicates_in_subsections(
    subsections: _t.Iterable[SubSection], version: str | None, ctx: Context
):
    seen_categories: set[str] = set()
    for subsection in subsections:
        match subsection.type:
            case SubSectionType.TRIVIA:
                pass
            case SubSectionType.CHANGES:
                if subsection.category in seen_categories:
                    ctx.issue(
                        "Found multiple sub-sections for `%s` category in release `%s`.",
                        subsection.category,
                        version,
                        pos=subsection,
                    )
                else:
                    seen_categories.add(subsection.category)


def check_order(sections: list[Section], ctx: Context):
    if (
        not sections
        or sections[0].type != SectionType.TRIVIA
        or not sections[0].subsections
        or not sections[0].subsections[0].content
        or sections[0].subsections[0].content[0].tag != "h1"
    ):
        ctx.issue(
            "Changelog must start with a first level heading.",
            pos=sections[0] if sections else None,
        )
        return
    last_version = None
    found_unordered_sections = False
    for section in sections:
        match section.type:
            case SectionType.TRIVIA:
                continue
            case SectionType.UNRELEASED:
                if last_version is not None:
                    ctx.issue(
                        "Section for unreleased changes must be first in the changelog.",
                        pos=section,
                    )
            case SectionType.RELEASE:
                if (
                    last_version
                    and section.parsed_version
                    and last_version < section.parsed_version
                ):
                    if not found_unordered_sections:
                        # Don't spam too many warnings.
                        ctx.issue(
                            "Sections are not ordered by release versions.",
                            pos=section,
                        )
                    found_unordered_sections = True
                elif section.parsed_version is not None:
                    last_version = section.parsed_version

        check_order_in_subsection(section.subsections, section.version, ctx)

    return found_unordered_sections


def check_order_in_subsection(
    subsections: list[SubSection], version: str | None, ctx: Context
):
    last_sort_key = None
    for subsection in subsections:
        match subsection.type:
            case SubSectionType.TRIVIA:
                continue
            case SubSectionType.CHANGES:
                if (
                    last_sort_key is not None
                    and subsection.sort_key is not None
                    and last_sort_key > subsection.sort_key
                ):
                    ctx.issue(
                        "Sub-sections in release `%s` are not ordered by preferred order.",
                        version,
                        pos=subsection,
                    )
                    return
                elif subsection.sort_key is not None:
                    last_sort_key = subsection.sort_key


def check_links(
    sections: list[Section],
    ctx: Context,
    can_trust_order: bool,
):
    if not ctx.config.add_release_link:
        for section in reversed(sections):
            if section.type is SectionType.TRIVIA:
                continue
            if section.version_link is not None:
                if section.type is SectionType.UNRELEASED:
                    release_name = "unreleased section"
                else:
                    release_name = f"release `{section.version}`"
                ctx.issue("Unexpected link for %s.", release_name, pos=section)
        return

    prev_tag: str | None = None
    for section in reversed(sections):
        if section.type is SectionType.TRIVIA:
            continue
        if section.type is SectionType.UNRELEASED and not can_trust_order:
            continue

        canonical_link, prev_tag = make_link_for_section(section, prev_tag, ctx)

        if section.type is SectionType.UNRELEASED:
            release_name = "unreleased section"
        else:
            release_name = f"release `{section.version}`"

        if canonical_link is None:
            if section.version_link is not None:
                ctx.issue(
                    f"Unexpected link for {release_name}.",
                    pos=section,
                )
        else:
            if section.version_link is None:
                if can_trust_order:
                    ctx.issue(
                        f"Missing link for {release_name}, should be <c path>%s</c>.",
                        canonical_link,
                        pos=section,
                    )
                else:
                    ctx.issue(
                        f"Missing link for {release_name}.",
                        pos=section,
                    )
            elif section.version_link != canonical_link:
                if can_trust_order:
                    ctx.issue(
                        f"Incorrect link for {release_name}, should be <c path>%s</c>.",
                        canonical_link,
                        pos=section,
                    )
                else:
                    ctx.issue(
                        f"Potentially incorrect link for {release_name}.",
                        pos=section,
                        severity=IssueSeverity.WEAK_WARNING,
                    )


def check_dates(
    sections: list[Section],
    ctx: Context,
    repo_versions: dict[str, yuio.git.Commit] | None,
):
    for section in sections:
        if section.type is not SectionType.RELEASE:
            continue
        if ctx.config.add_release_date and section.release_date_fmt is None:
            ctx.issue(
                "Missing date for release `%s`.",
                section.version,
                pos=section,
            )
        elif (
            ctx.config.add_release_date
            and repo_versions
            and section.version is not None
            and section.release_date is not None
            and (commit := repo_versions.get(section.version))
        ):
            if (
                commit.author_datetime.date() != section.release_date
                and commit.committer_datetime.date() != section.release_date
            ):
                ctx.issue(
                    "Release date for release `%s` is different from commit date `%s`.",
                    section.version,
                    commit.committer_datetime.date().isoformat(),
                    pos=section,
                    severity=IssueSeverity.WEAK_WARNING,
                )
        elif not ctx.config.add_release_date and section.release_date_fmt is None:
            ctx.issue(
                "Unexpected release date for release `%s`.",
                section.version,
                pos=section,
            )


def check_section_content(sections: list[Section], ctx: Context):
    is_first_section = True
    for section in sections:
        nodes = section.walk()
        if section.type is SectionType.TRIVIA and is_first_section:
            try:
                next(nodes)  # Skip first <h1>.
            except StopIteration:
                pass
        is_first_section = False
        for node in nodes:
            if node.tag == "h1":
                ctx.issue("Unexpected first level heading.", pos=node)
        if section.type is SectionType.RELEASE:
            if (
                not section.subsections
                and section.version
                and not section.version.startswith("0.")
            ):
                ctx.issue(
                    "Section for release `%s` is empty.",
                    section.version,
                    pos=section,
                    severity=IssueSeverity.WEAK_WARNING,
                )
            for subsection in section.subsections:
                if not subsection.content:
                    ctx.issue(
                        "Sub-section `%s` for release `%s` is empty.",
                        subsection.category,
                        section.version,
                        pos=section,
                        severity=IssueSeverity.WEAK_WARNING,
                    )
                    break


def check_tags(
    sections: list[Section], ctx: Context, repo_versions: dict[str, yuio.git.Commit]
):
    known_tags = set(repo_versions)
    releases = set(section.version for section in sections if section.version)
    if not_in_repo := releases - known_tags:
        ctx.issue(
            f"Missing tags for release{"" if len(not_in_repo) == 1 else "s"} "
            f"{_join_more(not_in_repo)}.",
            scope=IssueScope.EXTERNAL,
            severity=IssueSeverity.WEAK_WARNING,
        )
    if not_in_changelog := known_tags - releases:
        ctx.issue(
            f"Missing changelog sections for "
            f"release{"" if len(not_in_changelog) == 1 else "s"} "
            f"{_join_more(not_in_changelog)}.",
            scope=IssueScope.EXTERNAL,
            severity=IssueSeverity.WEAK_WARNING,
        )


def _join_more(strings: _t.Collection[str]) -> str:
    joined = ", ".join(f"`{s}`" for s in sorted(strings)[:5])
    if len(strings) > 5:
        joined += f" (+{len(strings) - 5} more)"
    return joined
