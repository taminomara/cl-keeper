from __future__ import annotations

import re
import typing as _t

from cl_keeper.context import Context, IssueCode, IssueScope
from cl_keeper.fix import make_link_for_section
from cl_keeper.model import (
    Changelog,
    ReleaseSection,
    RepoVersion,
    Section,
    SubSectionType,
    UnreleasedSection,
)


def check(
    changelog: Changelog, ctx: Context, repo_versions: dict[str, RepoVersion] | None
):
    check_duplicates(changelog.sections, ctx)
    found_unordered_sections = check_order(changelog.sections, ctx)
    check_links(
        changelog.sections,
        repo_versions,
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
        if section.is_unreleased():
            if seen_unreleased:
                ctx.issue(
                    IssueCode.DUPLICATE_RELEASES,
                    "Found multiple sections for unreleased changes",
                    pos=section,
                )
            seen_unreleased = True
            check_duplicates_in_subsections(section, ctx)
        elif release := section.as_release():
            if release.canonized_version in seen_versions:
                ctx.issue(
                    IssueCode.DUPLICATE_RELEASES,
                    "Found multiple sections for release `%s`",
                    release.version,
                    pos=section,
                )
            seen_versions.add(release.canonized_version)
            check_duplicates_in_subsections(section, ctx)


def check_duplicates_in_subsections(section: Section, ctx: Context):
    seen_categories: set[str] = set()
    for subsection in section.subsections:
        match subsection.type:
            case SubSectionType.TRIVIA:
                pass
            case SubSectionType.CHANGES:
                if subsection.category in seen_categories:
                    ctx.issue(
                        IssueCode.DUPLICATE_CHANGE_CATEGORIES,
                        f"Found multiple sub-sections for `%s` category in {section.what()}",
                        subsection.category,
                        pos=subsection,
                    )
                else:
                    seen_categories.add(subsection.category)


def check_order(sections: list[Section], ctx: Context):
    if (
        not sections
        or not sections[0].is_trivia()
        or not sections[0].subsections
        or not sections[0].subsections[0].content
        or sections[0].subsections[0].content[0].tag != "h1"
    ):
        ctx.issue(
            IssueCode.GENERAL_FORMATTING_ERROR,
            "Changelog must start with a first level heading",
            pos=sections[0] if sections else None,
        )
        return
    last_version = None
    found_unordered_sections = False
    for section in sections:
        if section.is_unreleased():
            if last_version is not None:
                ctx.issue(
                    IssueCode.RELEASE_ORDERING,
                    "Section for unreleased changes must be first in the changelog",
                    pos=section,
                )
            check_order_in_subsection(section, ctx)
        elif release := section.as_release():
            if (
                last_version
                and release.parsed_version
                and last_version < release.parsed_version
            ):
                if not found_unordered_sections:
                    # Don't spam too many warnings.
                    ctx.issue(
                        IssueCode.RELEASE_ORDERING,
                        "Sections are not ordered by release versions",
                        pos=section,
                    )
                found_unordered_sections = True
            elif release.parsed_version is not None:
                last_version = release.parsed_version
            check_order_in_subsection(section, ctx)

    return found_unordered_sections


def check_order_in_subsection(section: Section, ctx: Context):
    last_sort_key = None
    for subsection in section.subsections:
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
                        IssueCode.CHANGE_CATEGORY_ORDERING,
                        f"Sub-sections in {section.what()} are not ordered by preferred order",
                        pos=subsection,
                    )
                    return
                elif subsection.sort_key is not None:
                    last_sort_key = subsection.sort_key


def check_links(
    sections: list[Section],
    repo_versions: dict[str, RepoVersion] | None,
    ctx: Context,
    can_trust_order: bool,
):
    if not ctx.config.add_release_link:
        for section in reversed(sections):
            if not isinstance(section, (ReleaseSection, UnreleasedSection)):
                continue
            if section.version_link is not None:
                ctx.issue(
                    IssueCode.UNEXPECTED_RELEASE_LINK,
                    f"Unexpected link for {section.what()}",
                    pos=section,
                )
        return

    prev_tag: str | None = None
    for section in reversed(sections):
        if not isinstance(section, (ReleaseSection, UnreleasedSection)):
            continue
        if section.is_unreleased() and not can_trust_order:
            continue

        canonical_link, prev_tag = make_link_for_section(
            section, prev_tag, repo_versions, ctx
        )

        if canonical_link is None:
            if section.version_link is not None:
                ctx.issue(
                    IssueCode.UNEXPECTED_RELEASE_LINK,
                    f"Unexpected link for {section.what()}",
                    pos=section,
                )
        else:
            if section.version_link is None:
                if can_trust_order:
                    ctx.issue(
                        IssueCode.MISSING_RELEASE_LINK,
                        f"Missing link for {section.what()}, should be <c path>%s</c>",
                        canonical_link,
                        pos=section,
                    )
                else:
                    ctx.issue(
                        IssueCode.MISSING_RELEASE_LINK,
                        f"Missing link for {section.what()}",
                        pos=section,
                    )
            elif section.version_link != canonical_link:
                if can_trust_order:
                    ctx.issue(
                        IssueCode.MISSING_RELEASE_LINK,
                        f"Incorrect link for {section.what()}, should be <c path>%s</c>",
                        canonical_link,
                        pos=section,
                    )
                else:
                    ctx.issue(
                        IssueCode.INCORRECT_RELEASE_LINK,
                        f"Potentially incorrect link for {section.what()}",
                        pos=section,
                    )


def check_dates(
    sections: list[Section],
    ctx: Context,
    repo_versions: dict[str, RepoVersion] | None,
):
    for section in sections:
        release = section.as_release()
        if not release:
            continue
        if ctx.config.add_release_date and release.release_date_fmt is None:
            ctx.issue(
                IssueCode.MISSING_RELEASE_DATE,
                "Missing date for release `%s`",
                release.version,
                pos=section,
            )
        elif (
            ctx.config.add_release_date
            and repo_versions is not None
            and release.release_date is not None
            and (data := repo_versions.get(release.canonized_version))
        ):
            if (
                data.author_date != release.release_date
                and data.committer_date != release.release_date
            ):
                ctx.issue(
                    IssueCode.INCORRECT_RELEASE_DATE,
                    "Release date for release `%s` is different from commit date `%s`",
                    release.version,
                    data.committer_date.isoformat(),
                    pos=release,
                )
        elif not ctx.config.add_release_date and release.release_date_fmt is None:
            ctx.issue(
                IssueCode.UNEXPECTED_RELEASE_DATE,
                "Unexpected release date for release `%s`",
                release.version,
                pos=release,
            )


def check_section_content(sections: list[Section], ctx: Context):
    is_first_section = True
    lower_bound = ctx.config.parsed_ignore_missing_releases_before
    regex_bound = ctx.config.ignore_missing_releases_regexp
    for section in sections:
        nodes = section.walk()
        if section.is_trivia() and is_first_section:
            try:
                next(nodes)  # Skip first <h1>.
            except StopIteration:
                pass
        is_first_section = False
        for node in nodes:
            if node.tag == "h1":
                ctx.issue(
                    IssueCode.GENERAL_FORMATTING_ERROR,
                    "Unexpected first level heading",
                    pos=node,
                )
        if release := section.as_release():
            if (
                not release.subsections
                and release.parsed_version is not None
                and (lower_bound is None or release.parsed_version >= lower_bound)
                and (regex_bound is None or not re.search(regex_bound, release.version))
            ):
                ctx.issue(
                    IssueCode.EMPTY_RELEASE,
                    "Section for release `%s` is empty",
                    release.version,
                    pos=section,
                )
            for subsection in release.subsections:
                if not subsection.content:
                    ctx.issue(
                        IssueCode.EMPTY_CHANGE_CATEGORY,
                        "Sub-section `%s` for release `%s` is empty",
                        subsection.category,
                        release.version,
                        pos=section,
                    )
                    break


def check_tags(
    sections: list[Section], ctx: Context, repo_versions: dict[str, RepoVersion]
):
    known_versions = set(repo_versions)
    releases = set(
        release.canonized_version
        for section in sections
        if (release := section.as_release())
    )
    if not_in_repo := releases - known_versions:
        ctx.issue(
            IssueCode.MISSING_TAG_FOR_RELEASE,
            f"Missing tags for release{"" if len(not_in_repo) == 1 else "s"} "
            f"{_join_more(not_in_repo)}",
            scope=IssueScope.EXTERNAL,
        )
    lower_bound = ctx.config.parsed_ignore_missing_releases_before
    regex_bound = ctx.config.ignore_missing_releases_regexp
    not_in_changelog = []
    for data in repo_versions.values():
        if (
            data.canonized_version not in releases
            and data.parsed_version is not None
            and (lower_bound is None or data.parsed_version >= lower_bound)
            and (
                regex_bound is None
                or not re.search(regex_bound, data.canonized_version)
            )
        ):
            not_in_changelog.append(data.version)
    if not_in_changelog:
        ctx.issue(
            IssueCode.MISSING_RELEASE_FOR_TAG,
            f"Missing changelog sections for "
            f"release{"" if len(not_in_changelog) == 1 else "s"} "
            f"{_join_more(not_in_changelog)}",
            scope=IssueScope.EXTERNAL,
        )


def _join_more(strings: _t.Collection[str]) -> str:
    joined = ", ".join(f"`{s}`" for s in sorted(strings)[:5])
    if len(strings) > 5:
        joined += f" (+{len(strings) - 5} more)"
    return joined
