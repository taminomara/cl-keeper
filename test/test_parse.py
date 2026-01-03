import pathlib
import textwrap

import pytest
from packaging.version import Version as PyVersion
from semver import Version as SemverVersion

from cl_keeper.config import Config, VersionFormat
from cl_keeper.context import Context
from cl_keeper.model import Section, SubSection
from cl_keeper.parse import canonize_version, parse, parse_version


@pytest.mark.parametrize(
    ("format", "version", "expected"),
    [
        (VersionFormat.NONE, "whatever", None),
        (
            VersionFormat.SEMVER,
            "1.0.0-beta.0+12345",
            SemverVersion(1, 0, 0, "beta.0", "12345"),
        ),
        (VersionFormat.SEMVER_STRICT, "1.0.0", SemverVersion(1, 0, 0)),
        (VersionFormat.SEMVER_STRICT, "1.0.0-alpha1", SemverVersion(1, 0, 0, "alpha1")),
        (VersionFormat.SEMVER_STRICT, "1.0.0-beta1", SemverVersion(1, 0, 0, "beta1")),
        (VersionFormat.SEMVER_STRICT, "1.0.0-rc1", SemverVersion(1, 0, 0, "rc1")),
        (VersionFormat.SEMVER_STRICT, "1.0", None),
        (VersionFormat.SEMVER_STRICT, "1.0.0.0", None),
        (VersionFormat.SEMVER_STRICT, "1.0.0-beta.1", None),
        (VersionFormat.SEMVER_STRICT, "1.0.0-foo1", None),
        (VersionFormat.PYTHON, "1.0.0", PyVersion("1.0.0")),
        (VersionFormat.PYTHON, "1.0.0b0", PyVersion("1.0.0b0")),
        (VersionFormat.PYTHON, "1.0.0-beta.0", PyVersion("1.0.0b0")),
        (VersionFormat.PYTHON, "1.0.0.post0+foo", PyVersion("1.0.0.post0+foo")),
        (VersionFormat.PYTHON, "2!1.0.0", PyVersion("2!1.0.0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0", PyVersion("1.0.0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0a0", PyVersion("1.0.0a0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0b0", PyVersion("1.0.0b0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0rc0", PyVersion("1.0.0rc0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0.post0", PyVersion("1.0.0.post0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0a0.post0", PyVersion("1.0.0a0.post0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0b0.post0", PyVersion("1.0.0b0.post0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0rc0.post0", PyVersion("1.0.0rc0.post0")),
        (VersionFormat.PYTHON_STRICT, "2!1.0.0", PyVersion("2!1.0.0")),
        (VersionFormat.PYTHON_STRICT, "1.0.0-a0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0-alpha0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0a.0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0alpha.0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0-post0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0post.0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0.post-0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0", PyVersion("1.0.0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-alpha0", PyVersion("1.0.0a0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-beta0", PyVersion("1.0.0b0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-rc0", PyVersion("1.0.0rc0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-post0", PyVersion("1.0.0.post0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-alpha0.post0", PyVersion("1.0.0a0.post0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-beta0.post0", PyVersion("1.0.0b0.post0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-rc0.post0", PyVersion("1.0.0rc0.post0")),
        (VersionFormat.PYTHON_SEMVER, "2!1.0.0", PyVersion("2!1.0.0")),
        (VersionFormat.PYTHON_SEMVER, "1.0.0a0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0b0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0rc0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0.post0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0a0.post0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0b0.post0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0rc0.post0", None),
    ],
)
def test_parse_version(format, version, expected):
    assert parse_version(version, Config(version_format=format)) == expected


@pytest.mark.parametrize(
    ("format", "version", "expected"),
    [
        (VersionFormat.NONE, "whatever", None),
        (VersionFormat.SEMVER, "1.0.0-beta.0+12345", "1.0.0-beta.0+12345"),
        (VersionFormat.SEMVER_STRICT, "1.0.0", "1.0.0"),
        (VersionFormat.SEMVER_STRICT, "1.0.0-alpha1", "1.0.0-alpha1"),
        (VersionFormat.SEMVER_STRICT, "1.0.0-beta1", "1.0.0-beta1"),
        (VersionFormat.SEMVER_STRICT, "1.0.0-rc1", "1.0.0-rc1"),
        (VersionFormat.SEMVER_STRICT, "1.0", None),
        (VersionFormat.SEMVER_STRICT, "1.0.0.0", None),
        (VersionFormat.SEMVER_STRICT, "1.0.0-beta.1", None),
        (VersionFormat.SEMVER_STRICT, "1.0.0-foo1", None),
        (VersionFormat.PYTHON, "1.0.0", "1.0.0"),
        (VersionFormat.PYTHON, "1.0.0b0", "1.0.0b0"),
        (VersionFormat.PYTHON, "1.0.0-beta.0", "1.0.0b0"),
        (VersionFormat.PYTHON, "1.0.0-beta.post0", "1.0.0b0.post0"),
        (VersionFormat.PYTHON, "2!1.0.0", "2!1.0.0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0", "1.0.0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0a0", "1.0.0a0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0b0", "1.0.0b0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0rc0", "1.0.0rc0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0.post0", "1.0.0.post0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0a0.post0", "1.0.0a0.post0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0b0.post0", "1.0.0b0.post0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0rc0.post0", "1.0.0rc0.post0"),
        (VersionFormat.PYTHON_STRICT, "2!1.0.0", "2!1.0.0"),
        (VersionFormat.PYTHON_STRICT, "1.0.0-a0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0-alpha0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0a.0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0alpha.0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0-post0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0post.0", None),
        (VersionFormat.PYTHON_STRICT, "1.0.0.post-0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0", "1.0.0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-alpha0", "1.0.0-alpha0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-beta0", "1.0.0-beta0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-rc0", "1.0.0-rc0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-post0", "1.0.0-post0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-alpha0.post0", "1.0.0-alpha0.post0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-beta0.post0", "1.0.0-beta0.post0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0-rc0.post0", "1.0.0-rc0.post0"),
        (VersionFormat.PYTHON_SEMVER, "2!1.0.0", "2!1.0.0"),
        (VersionFormat.PYTHON_SEMVER, "2!1.0.0-beta0", "2!1.0.0-beta0"),
        (VersionFormat.PYTHON_SEMVER, "1.0.0a0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0b0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0rc0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0.post0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0a0.post0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0b0.post0", None),
        (VersionFormat.PYTHON_SEMVER, "1.0.0rc0.post0", None),
    ],
)
def test_canonize(format, version, expected):
    config = Config(version_format=format)
    assert canonize_version(parse_version(version, config), config) == expected


DEFAULT_ITEM_CATEGORIES_CONFIG = Config(
    use_default_item_categories=True
).process_config()


@pytest.mark.parametrize(
    ("input", "config"),
    [
        pytest.param(
            """
            """,
            None,
            id="empty",
        ),
        pytest.param(
            """
            """,
            None,
            id="only_heading",
        ),
        pytest.param(
            """
            ## Unreleased
            """,
            None,
            id="unreleased_simple",
        ),
        pytest.param(
            """
            ## [Unreleased]
            """,
            None,
            id="unreleased_unlinked",
        ),
        pytest.param(
            """
            ## [Unreleased]

            [Unreleased]: https://example.com/
            """,
            None,
            id="unreleased_linked",
        ),
        pytest.param(
            """
            ## something-something unreleased, maybe?
            """,
            None,
            id="unreleased_broken",
        ),
        pytest.param(
            """
            ## Unreleased
            ### Added
            - a
            - b
            ### Removed
            - c
            - d
            ### Unknown
            - e
            - f
            """,
            None,
            id="unreleased_subsections",
        ),
        pytest.param(
            """
            ## 1.0.0
            """,
            None,
            id="release",
        ),
        pytest.param(
            """
            ## v1.0.0
            """,
            None,
            id="release_with_prefix",
        ),
        pytest.param(
            """
            ## [1.0.0]
            """,
            None,
            id="release_unlinked",
        ),
        pytest.param(
            """
            ## [1.0.0] - 2020-01-01
            """,
            None,
            id="release_unlinked_with_date",
        ),
        pytest.param(
            """
            ## 2020-01-01 [1.0.0]
            """,
            None,
            id="release_unlinked_with_date_before_version",
        ),
        pytest.param(
            """
            ## [1.0.0]
            [1.0.0]: https://example.com/
            """,
            None,
            id="release_linked",
        ),
        pytest.param(
            """
            ## ~ 1.0.0 ~ 2020-01-01
            """,
            None,
            id="release_with_decorations_error",
        ),
        pytest.param(
            """
            ## ~ 1.0.0 ~ 2020-01-01
            """,
            Config(
                version_decorations=("~ ", " ~"),
                release_date_decorations=(" ", ""),
            ),
            id="release_with_decorations_ok",
        ),
        pytest.param(
            """
            ## 1.0.0 - 2020-01-01
            """,
            None,
            id="release_with_date",
        ),
        pytest.param(
            """
            ## 1.0.0 - 2020-20-20
            """,
            None,
            id="release_with_broken_date",
        ),
        pytest.param(
            """
            ## 2020-01-01 - 1.0.0
            """,
            None,
            id="release_with_date_before_version",
        ),
        pytest.param(
            """
            ## 1.0.0 - [YANKED]
            """,
            None,
            id="release_with_postfix",
        ),
        pytest.param(
            """
            ## 1.0.0 - 2020-01-01 - [YANKED]
            """,
            None,
            id="release_with_date_and_postfix",
        ),
        pytest.param(
            """
            ## 2020-01-01 - 1.0.0 - [YANKED]
            """,
            None,
            id="release_with_date_before_version_and_postfix",
        ),
        pytest.param(
            """
            ## 1.0.0 - (2020-01-01) - [YANKED]
            """,
            None,
            id="release_with_date_and_postfix_braces",
        ),
        pytest.param(
            """
            ## 2020-01-01 - (1.0.0) - [YANKED]
            """,
            None,
            id="release_with_date_before_version_and_postfix_braces",
        ),
        pytest.param(
            """
            # Changelog

            ## [Unreleased]

            ## [1.0.0] - 2020-01-01

            ### Added

            - foo
            - bar

            ### Removed

            - baz

            ## [0.0.0-beta3]

            - Beta pre-release.

            [unreleased]: https://example.com/unreleased
            [1.0.0]: https://example.com/1.0.0
            [0.0.0-beta3]: https://example.com/0.0.0-beta3
            """,
            None,
            id="multiple_releases_with_sections",
        ),
        pytest.param(
            """
            # Changelog

            ## [Unreleased]

            ## [1.0.0] - 2020-01-01

            ### Added

            - foo
            - bar

            # What??

            ### Removed

            - baz

            ## [0.0.0-beta3]

            - Beta pre-release.

            [unreleased]: https://example.com/unreleased
            [1.0.0]: https://example.com/1.0.0
            [0.0.0-beta3]: https://example.com/0.0.0-beta3
            """,
            None,
            id="first_level_heading_in_the_middle",
        ),
        pytest.param(
            """
            ### Added
            - foo
            """,
            None,
            id="subsection_not_attached",
        ),
        pytest.param(
            """
            ## 1.0.0
            ### ~ added ~
            - foo
            """,
            None,
            id="subsection_format_error",
        ),
        pytest.param(
            """
            ## 1.0.0
            ### ~ added ~
            - foo
            """,
            Config(extra_change_categories={"added": "~ added ~"}).process_config(),
            id="subsection_format_ok",
        ),
        pytest.param(
            """
            ## who is this?
            It's a me, Mario!
            """,
            None,
            id="unrecognized_section",
        ),
        pytest.param(
            """
            ## 1.0.0.b10
            """,
            None,
            id="version_canonization_fail",
        ),
        pytest.param(
            """
            ## 1.0.0.b10
            """,
            Config(version_format=VersionFormat.PYTHON),
            id="version_canonization_ok",
        ),
        pytest.param(
            """
            ## 1.0.0.b10
            """,
            Config(version_format=VersionFormat.NONE),
            id="version_canonization_none",
        ),
        pytest.param(
            """
            ## Unreleased
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_trivia",
        ),
        pytest.param(
            """
            ## Unreleased
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_trivia_format_error",
        ),
        pytest.param(
            """
            ## Unreleased
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_trivia_unknown",
        ),
        pytest.param(
            """
            ## Unreleased
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_trivia_multiple_change_lists",
        ),
        pytest.param(
            """
            ## Unreleased
            ### Added
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_sub_section",
        ),
        pytest.param(
            """
            ## Unreleased
            ### Added
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_sub_section_format_error",
        ),
        pytest.param(
            """
            ## Unreleased
            ### Added
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_sub_section_unknown",
        ),
        pytest.param(
            """
            ## Unreleased
            ### Added
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_unversioned_sub_section_multiple_change_lists",
        ),
        pytest.param(
            """
            ## 1.0.0
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_trivia",
        ),
        pytest.param(
            """
            ## 1.0.0
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_trivia_format_error",
        ),
        pytest.param(
            """
            ## 1.0.0
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_trivia_unknown",
        ),
        pytest.param(
            """
            ## 1.0.0
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_trivia_multiple_change_lists",
        ),
        pytest.param(
            """
            ## 1.0.0
            ### Added
            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_sub_section",
        ),
        pytest.param(
            """
            ## 1.0.0
            ### Added
            - added feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_sub_section_format_error",
        ),
        pytest.param(
            """
            ## 1.0.0
            ### Added
            - [added] feature
            - [bamboozled] by unknown item category
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_sub_section_unknown",
        ),
        pytest.param(
            """
            ## 1.0.0
            ### Added
            - [added] feature

            content

            - [added] feature
            """,
            DEFAULT_ITEM_CATEGORIES_CONFIG,
            id="item_categories_in_release_sub_section_multiple_change_lists",
        ),
    ],
)
def test_parse(input: str, config, data_regression):

    input = textwrap.dedent(input).strip()
    ctx = Context(
        pathlib.Path("__test__"),
        pathlib.Path("__test__"),
        input,
        config or Config().process_config(),
        False,
        None,  # type: ignore
        False,
    )

    changelog = parse(ctx)

    data = dict(
        sections=[_serialize_section(section) for section in changelog.sections],
        messages=_serialize_messages(ctx),
    )

    data_regression.check(data)


def _serialize_section(section: Section):
    subsections = [
        _serialize_subsection(subsection) for subsection in section.subsections
    ]
    if release := section.as_release():
        return dict(
            type="RELEASE",
            version=release.version,
            parsed_version=release.parsed_version and str(release.parsed_version),
            canonized_version=release.canonized_version,
            version_link=release.version_link,
            version_label=release.version_label,
            release_date=release.release_date and release.release_date.isoformat(),
            release_date_fmt=release.release_date_fmt,
            release_comment=release.release_comment,
            subsections=subsections,
        )
    elif unreleased := section.as_unreleased():
        return dict(
            type="UNRELEASED",
            version_link=unreleased.version_link,
            version_label=unreleased.version_label,
            subsections=subsections,
        )
    else:
        return dict(
            type="TRIVIA",
            subsections=subsections,
        )


def _serialize_subsection(subsection: SubSection):
    return dict(
        type=subsection.type.value,
        category_kind=subsection.category_kind.value,
        category=subsection.category,
        sort_key=subsection.sort_key,
    )


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
