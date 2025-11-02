import datetime
import pathlib
import textwrap

import pytest
import semver

from cl_keeper.check import check
from cl_keeper.config import (
    Config,
    IssueCode,
    IssueSeverity,
    LinkTemplates,
    VersionFormat,
)
from cl_keeper.context import Context
from cl_keeper.model import RepoVersion
from cl_keeper.parse import parse

EXAMPLE_LINK_TEMPLATES = LinkTemplates(
    "https://example.com/{prev_tag}..{tag}",
    "https://example.com/{prev_tag}..HEAD",
    "https://example.com/{tag}",
    {},
)

DEFAULT_ITEM_CATEGORIES_CONFIG = Config(
    use_default_item_categories=True,
    add_release_date=False,
    add_release_link=False,
    extra_item_categories={
        "programmed": "",
    },
    extra_item_categories_map={
        r"(?im)programmed": "programmed",
    },
).process_config()


@pytest.mark.parametrize(
    "input,config,link_templates",
    [
        pytest.param(
            """
            """,
            None,
            None,
            id="empty",
        ),
        pytest.param(
            """
            # Changelog
            """,
            None,
            None,
            id="just_heading",
        ),
        pytest.param(
            """
            # Some random file
            """,
            None,
            None,
            id="just_heading_not_changelog",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="empty_release",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0-beta0] - 2025-01-01
            [1.0.0-beta0]: https://example.com/
            """,
            None,
            None,
            id="empty_pre_release",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0 - 2025-01-01
            Content
            """,
            None,
            None,
            id="missing_link_empty_link_template",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0 - 2025-01-01
            Content
            """,
            None,
            LinkTemplates(
                "https://example.com/",
                "https://example.com/",
                "https://example.com/",
                {},
            ),
            id="missing_link",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0 - 2025-01-01
            Content
            """,
            Config(add_release_link=False),
            None,
            id="missing_link_no_links",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/
            """,
            Config(add_release_link=False),
            None,
            id="unexpected_link",
        ),
        pytest.param(
            """
            # Changelog
            ## [Unreleased]
            ## [2.0.0] - 2025-01-01
            Content
            ## [1.0.0] - 2025-01-01
            Content

            [2.0.0]: https://example.com/
            [1.0.0]: https://example.com/
            [Unreleased]: https://example.com/
            """,
            Config(),
            EXAMPLE_LINK_TEMPLATES,
            id="wrong_links",
        ),
        pytest.param(
            """
            # Changelog
            ## [2.0.0] - 2025-01-01
            Content
            ## [1.0.0] - 2025-01-01
            Content

            [2.0.0]: https://example.com/
            [1.0.0]: https://example.com/
            """,
            Config(),
            EXAMPLE_LINK_TEMPLATES,
            id="wrong_links_no_unreleased",
        ),
        pytest.param(
            """
            # Changelog
            ## [Unreleased]

            [Unreleased]: https://example.com/
            """,
            Config(add_release_link=False),
            None,
            id="unexpected_unreleased_link",
        ),
        pytest.param(
            """
            # Changelog
            ## [Unreleased]

            [Unreleased]: https://example.com/
            """,
            # link is required, but it's impossible to make one
            Config(add_release_link=True),
            None,
            id="unexpected_unreleased_link_2",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ## [1.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="missing_unreleased_link_empty_template",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ## [1.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/v1.0.0
            """,
            None,
            EXAMPLE_LINK_TEMPLATES,
            id="missing_unreleased",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content
            ## [2.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/v2.0.0..v1.0.0
            [2.0.0]: https://example.com/v2.0.0
            """,
            None,
            EXAMPLE_LINK_TEMPLATES,
            id="wrong_links_and_order",
        ),
        pytest.param(
            """
            # Changelog
            ## [2.0.0] - 2025-01-01
            Content
            ## [1.0.0] - 2025-01-01
            Content

            [2.0.0]: https://example.com/v2.0.0
            [1.0.0]: https://example.com/v1.0.0..v2.0.0
            """,
            None,
            EXAMPLE_LINK_TEMPLATES,
            id="wrong_links_right_order",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content
            ## [2.0.0] - 2025-01-01
            Content

            [2.0.0]: https://example.com/v1.0.0..v2.0.0
            [1.0.0]: https://example.com/v1.0.0
            """,
            None,
            EXAMPLE_LINK_TEMPLATES,  # TODO: improve detection or sorting?
            id="right_links_wrong_order",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content
            ## [2.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/
            [2.0.0]: https://example.com/
            """,
            None,
            None,
            id="wrong_order",
        ),
        pytest.param(
            """
            # Changelog
            ## [2.0.0] - 2025-01-01
            Content
            ## [1.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/v1.0.0..v2.0.0
            [2.0.0]: https://example.com/v1.0.0
            """,
            Config(version_format=VersionFormat.NONE),
            None,
            id="cant_check_order",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content
            ## [Unreleased]

            [1.0.0]: https://example.com/
            [Unreleased]: https://example.com/
            """,
            None,
            None,
            id="unreleased_not_first",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content
            ## [2.0.0] - 2025-01-01
            Content
            ## [Unreleased]

            [1.0.0]: https://example.com/
            [2.0.0]: https://example.com/
            [Unreleased]: https://example.com/
            """,
            None,
            None,
            id="unreleased_not_first_and_wrong_order",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            ### Removed
            Content
            ### Added
            Content

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="wrong_order_of_subsections",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            ### Removed

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="empty_subsection",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            ### What?

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="empty_unknown_subsection",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0]
            Content

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="missing_release_date",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            Content

            [1.0.0]: https://example.com/
            """,
            Config(add_release_date=False),
            None,
            id="unexpected_release_date",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0]
            Content

            [1.0.0]: https://example.com/
            """,
            Config(add_release_date=False),
            None,
            id="missing_release_date_no_release_date",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            - Content

              # First level heading??

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="unexpected_first_level_heading",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            - Content
            ## [1.0.0] - 2025-01-01
            - Content

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="duplicate_releases",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0b0] - 2025-01-01
            - Content
            ## [1.0.0beta0] - 2025-01-01
            - Content

            [1.0.0b0]: https://example.com/
            [1.0.0beta0]: https://example.com/
            """,
            Config(version_format=VersionFormat.PYTHON),
            None,
            id="duplicate_releases_normalize_version",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            - Content
            ## [1.0.0] - 2025-01-01
            - Content

            [1.0.0]: https://example.com/v1.0.0
            """,
            None,
            EXAMPLE_LINK_TEMPLATES,
            id="duplicate_releases_wrong_links",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0b0] - 2025-01-01
            - Content
            ## [1.0.0beta0] - 2025-01-01
            - Content

            [1.0.0b0]: https://example.com/v1.0.0beta0
            [1.0.0beta0]: https://example.com/v1.0.0beta0
            """,
            Config(version_format=VersionFormat.PYTHON),
            EXAMPLE_LINK_TEMPLATES,
            id="duplicate_releases_normalize_version_wrong_links",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            ### Added
            foo
            ### Added
            bar

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="duplicate_subsections",
        ),
        pytest.param(
            """
            # Changelog
            ## [1.0.0] - 2025-01-01
            ### Add
            foo
            ### Added
            bar

            [1.0.0]: https://example.com/
            """,
            None,
            None,
            id="duplicate_subsections_normalize",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ## Unreleased
            """,
            None,
            None,
            id="duplicate_unreleased",
        ),
        pytest.param(
            """
            # Changelog
            ## Some trivia section
            ### This is an unknown subsection
            content
            ### This is an unknown empty subsection
            ### This is a subsection duplicate
            content
            ### This is a subsection duplicate
            content
            """,
            None,
            None,
            id="unknown_subsections_in_trivia_sections",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_trivia",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_trivia_format_error",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            - programmed a feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_trivia_no_canonical_format",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_trivia_unknown",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_trivia_multiple_change_lists",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            - [changed] something
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_trivia_order",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ### Added
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_sub_section",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ### Added
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_sub_section_format_error",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ### Added
            - programmed a feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_sub_section_no_canonical_format",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ### Added
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_sub_section_unknown",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ### Added
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_sub_section_multiple_change_lists",
        ),
        pytest.param(
            """
            # Changelog
            ## Unreleased
            ### Added
            - [changed] something
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_unversioned_sub_section_order",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_trivia",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_trivia_format_error",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            - programmed a feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_trivia_no_canonical_format",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_trivia_unknown",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_trivia_multiple_change_lists",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            - [changed] something
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_trivia_order",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            ### Added
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_sub_section",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            ### Added
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_sub_section_format_error",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            ### Added
            - programmed a feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_sub_section_no_canonical_format",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            ### Added
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_sub_section_unknown",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            ### Added
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_sub_section_multiple_change_lists",
        ),
        pytest.param(
            """
            # Changelog
            ## 1.0.0
            ### Added
            - [changed] something
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            None,
            id="item_categories_in_release_sub_section_order",
        ),
    ],
)
def test_check(input: str, config, link_templates, data_regression):
    input = textwrap.dedent(input).strip()
    ctx = Context(
        pathlib.Path("__test__"),
        input,
        config or Config(),
        False,
        link_templates or LinkTemplates("", "", "", {}),
    )

    changelog = parse(ctx)
    check(changelog, ctx, None)

    data = _serialize_messages(ctx)

    data_regression.check(data)


def test_check_release_dates(data_regression):
    input = textwrap.dedent(
        """
        # Changelog
        ## 1.0.2 - 2025-01-30
        Content
        ## 1.0.1 - 2025-01-20
        Content
        ## 1.0.0 - 2025-01-10
        Content
    """
    ).strip()
    ctx = Context(
        pathlib.Path("__test__"),
        input,
        Config(add_release_link=False),
        False,
        LinkTemplates("", "", "", {}),
    )

    changelog = parse(ctx)
    check(
        changelog,
        ctx,
        {
            "1.0.0": RepoVersion(
                version="1.0.0",
                parsed_version=None,
                canonized_version="1.0.0",
                author_date=datetime.date(2025, 1, 10),
                committer_date=datetime.date(2025, 1, 10),
            ),
            "1.0.1": RepoVersion(
                version="1.0.1",
                parsed_version=None,
                canonized_version="1.0.1",
                author_date=datetime.date(2025, 1, 20),
                committer_date=datetime.date(2025, 1, 25),
            ),
            "1.0.2": RepoVersion(
                version="1.0.2",
                parsed_version=None,
                canonized_version="1.0.2",
                author_date=datetime.date(2025, 1, 25),
                committer_date=datetime.date(2025, 1, 26),
            ),
        },
    )

    data = _serialize_messages(ctx)

    data_regression.check(data)


def _repo_version(version):
    return RepoVersion(
        version=version,
        parsed_version=semver.Version.parse(version),  # type: ignore
        canonized_version=version,
        author_date=datetime.date(2025, 1, 25),
        committer_date=datetime.date(2025, 1, 26),
    )


def test_check_tags(data_regression):
    input = textwrap.dedent(
        """
        # Changelog
        ## 1.0.2
        Content
        ## 1.0.1
        Content
        ## 1.0.0-rc0
        Content
        ## 1.0.0-beta0
        Content
        ## 0.0.2
        Content
        ## 0.0.1
        Content
    """
    ).strip()
    ctx = Context(
        pathlib.Path("__test__"),
        input,
        Config(
            add_release_link=False,
            add_release_date=False,
            ignore_missing_releases_before="1.0.0",
        ),
        False,
        LinkTemplates("", "", "", {}),
    )

    changelog = parse(ctx)

    check(
        changelog,
        ctx,
        {
            "1.0.1": _repo_version("1.0.1"),
            "1.0.0": _repo_version("1.0.0"),
            "1.0.0-rc0": _repo_version("1.0.0-rc0"),
            "1.0.0-alpha1": _repo_version("1.0.0-alpha1"),
            "0.0.1": _repo_version("0.0.1"),
            "0.0.0": _repo_version("0.0.0"),
        },
    )

    data = _serialize_messages(ctx)

    data_regression.check(data)


def test_override_severity(data_regression):
    input = textwrap.dedent(
        """
        # Changelog
        ## 1.0.0
        Content
    """
    ).strip()
    ctx = Context(
        pathlib.Path("__test__"),
        input,
        Config(
            severity={
                IssueCode.MISSING_RELEASE_LINK: IssueSeverity.INFO,
                IssueCode.MISSING_RELEASE_DATE: IssueSeverity.NONE,
            }
        ),
        False,
        LinkTemplates("", "", "", {}),
    )

    changelog = parse(ctx)
    check(changelog, ctx, None)

    data = _serialize_messages(ctx)

    data_regression.check(data)


def test_override_severity_strict(data_regression):
    input = textwrap.dedent(
        """
        # Changelog
        ## 1.0.0
        Content
    """
    ).strip()
    ctx = Context(
        pathlib.Path("__test__"),
        input,
        Config(
            severity={
                IssueCode.MISSING_RELEASE_LINK: IssueSeverity.INFO,
                IssueCode.MISSING_RELEASE_DATE: IssueSeverity.NONE,
            }
        ),
        True,
        LinkTemplates("", "", "", {}),
    )

    changelog = parse(ctx)
    check(changelog, ctx, None)

    data = _serialize_messages(ctx)

    data_regression.check(data)


def _serialize_messages(ctx: Context):
    return [
        dict(
            mag=msg % args if args else msg,
            pos=pos,
            code=code.value,
            scope=scope.value,
            severity=severity.value,
        )
        for msg, args, pos, code, scope, severity in ctx._messages  # type: ignore
    ]
