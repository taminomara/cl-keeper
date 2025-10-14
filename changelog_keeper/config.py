from __future__ import annotations

import enum
import functools
import pathlib
import typing as _t
from dataclasses import dataclass

import yuio.app
import yuio.config
import yuio.parse


class Wrapping(enum.Enum):
    NO = "no"
    KEEP = "keep"


class IssueSeverity(enum.Enum):
    """
    Severity of the issue.

    """

    #: Error.
    ERROR = 4

    #: Warning.
    WARNING = 3

    #: Weak warning.
    WEAK_WARNING = 2

    #: Info.
    INFO = 1

    #: Not displayed.
    NONE = 0


class IssueCode(enum.Enum):
    #: A formatting error related to the general structure of the changelog.
    GENERAL_FORMATTING_ERROR = "GeneralFormattingError"

    #: Release version doesn't follow the requested specification.
    INVALID_VERSION = "InvalidVersion"

    #: Tag format doesn't follow the requested versioning specification.
    #:
    #: To disable all repository checks, set `check_repo_tags` to ``False``.
    INVALID_TAG = "InvalidTag"

    #: Found a tag that has no associated release.
    #:
    #: To suppress this error for all versions before the given one,
    #: set `ignore_missing_releases_before`. To disable all repository checks,
    #: set `check_repo_tags` to ``False``.
    MISSING_RELEASE_FOR_TAG = "MissingReleaseForTag"

    #: Found a release that has no associated tag in the repository.
    #:
    #: To disable all repository checks, set `check_repo_tags` to ``False``.
    MISSING_TAG_FOR_RELEASE = "MissingTagForRelease"

    #: Releases are not ordered according to their versions.
    #:
    #: Releases are compared according to the chosen versioning specification.
    RELEASE_ORDERING = "ReleaseOrdering"

    #: Heading for unreleased changes doesn't meet formatting requirements.
    #:
    #: Heading format is controlled by `unreleased_name`.
    UNRELEASED_HEADING_FORMAT = "UnreleasedHeadingFormat"

    #: Heading for a release doesn't meet formatting requirements.
    RELEASE_HEADING_FORMAT = "ReleaseHeadingFormat"

    #: Release date can't be parsed.
    #:
    #: This usually indicates that the release date is incorrect. For example,
    #: it refers to a day that doesn't exist in the calendar.
    INVALID_RELEASE_DATE = "InvalidReleaseDate"

    #: Release date is missing.
    #:
    #: `add_release_date` is ``True``, but release date is missing.
    MISSING_RELEASE_DATE = "MissingReleaseDate"

    #: Release date should not be present.
    #:
    #: `add_release_date` is ``False``, but release date is present.
    UNEXPECTED_RELEASE_DATE = "UnexpectedReleaseDate"

    #: Release link is missing.
    #:
    #: `add_release_link` is ``True``, but release link is missing.
    MISSING_RELEASE_LINK = "MissingReleaseLink"

    #: Release link should not be present.
    #:
    #: `add_release_link` is ``False``, but release link is present.
    UNEXPECTED_RELEASE_LINK = "UnexpectedReleaseLink"

    #: Release date doesn't match date of the release commit.
    #:
    #: To disable all repository checks, set `check_repo_tags` to ``False``.
    INCORRECT_RELEASE_DATE = "IncorrectReleaseDate"

    #: Release link is incorrect.
    #:
    #: Release links are generated using `release_link_preset`
    #: and `release_link_template`. We use order of releases from the changelog
    #: to generate links for commit ranges.
    INCORRECT_RELEASE_LINK = "IncorrectReleaseLink"

    #: Found multiple releases for the same version.
    DUPLICATE_RELEASES = "DuplicateReleases"

    #: Section for a release is empty.
    #:
    #: To ignore empty sections prior to some version,
    #: set `ignore_missing_releases_before`.
    EMPTY_RELEASE = "EmptyRelease"

    #: Order of sub-sections within a release doesn't match
    #: the one given in `change_categories`.
    CHANGE_CATEGORY_ORDERING = "ChangeCategoryOrdering"

    #: Heading for a change category doesn't meet formatting requirements.
    CHANGE_CATEGORY_HEADING_FORMAT = "ChangeCategoryHeadingFormat"

    #: Heading for a change category doesn't appear in `change_categories_map`.
    UNKNOWN_CHANGE_CATEGORY = "UnknownChangeCategory"

    #: Found multiple release sub-sections with the same title.
    DUPLICATE_CHANGE_CATEGORIES = "DuplicateChangeCategories"

    #: Found a release sub-section without content.
    EMPTY_CHANGE_CATEGORY = "EmptyChangeCategory"

    def default_severity(self) -> IssueSeverity:
        match self:
            case self.INVALID_VERSION:
                return IssueSeverity.ERROR
            case self.MISSING_RELEASE_FOR_TAG:
                return IssueSeverity.WEAK_WARNING
            case self.MISSING_TAG_FOR_RELEASE:
                return IssueSeverity.WEAK_WARNING
            case self.RELEASE_ORDERING:
                return IssueSeverity.ERROR
            case self.INVALID_RELEASE_DATE:
                return IssueSeverity.ERROR
            case self.DUPLICATE_RELEASES:
                return IssueSeverity.ERROR
            case self.EMPTY_RELEASE:
                return IssueSeverity.WARNING
            case self.INCORRECT_RELEASE_DATE:
                return IssueSeverity.WEAK_WARNING
            case self.DUPLICATE_CHANGE_CATEGORIES:
                return IssueSeverity.ERROR
            case self.EMPTY_CHANGE_CATEGORY:
                return IssueSeverity.ERROR
            case _:
                return IssueSeverity.WARNING


@dataclass
class LinkTemplates:
    template: str
    template_last: str
    template_first: str
    vars: dict[str, str]

    def has_unresolved_links(self):
        return not self.template or not self.template_last or not self.template_first

    def update(self, rhs: LinkTemplates):
        self.template = self.template or rhs.template
        self.template_last = self.template_last or rhs.template_last
        self.template_first = self.template_first or rhs.template_first
        self.update_vars(rhs.vars)
        return self

    def update_vars(self, vars: dict[str, str]):
        for k, v in vars.items():
            self.vars.setdefault(k, v)
        return self


class ReleaseLinkPreset(enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"

    def get_links(self) -> LinkTemplates:
        match self:
            case ReleaseLinkPreset.GITHUB:
                return LinkTemplates(
                    "https://{host}/{repo}/compare/{prev_tag}...{tag}",
                    "https://{host}/{repo}/compare/{prev_tag}...HEAD",
                    "https://{host}/{repo}/releases/tag/{tag}",
                    {},
                )
            case ReleaseLinkPreset.GITLAB:
                return LinkTemplates(
                    "https://{host}/{repo}/-/compare/{prev_tag}...{tag}",
                    "https://{host}/{repo}/-/compare/{prev_tag}...HEAD",
                    "https://{host}/{repo}/-/tags/{tag}",
                    {},
                )


class TagFormat(enum.Enum):
    """
    Specification for versioning formats.

    Different settings affect parsing versions and sorting changelog entries.

    .. list-table:: Syntax overview
        :header-rows: 1

        * - Schema
          - Release
          - Pre-release
          - Post-release
          - Post-release of a pre-release

        * - :attr:`~TagFormat.SEMVER`
          - ``1.0.0``
          - ``1.0.0-b``, ``1.0.0-b0``, ``1.0.0-beta0``, etc.
          - not supported
          - not supported
        * - :attr:`~TagFormat.SEMVER_STRICT`
          - ``1.0.0``
          - ``1.0.0-beta0``
          - not supported
          - not supported
        * - :attr:`~TagFormat.PYTHON`
          - ``1.0.0``
          - ``1.0.0b0``, ``1.0.0-beta.0``, etc.
          - ``1.0.0post0``, ``1.0.0-rev.0``, etc.
          - ``1.0.0b1.post2``, ``1.0.0-beta.1post2``, etc.
        * - :attr:`~TagFormat.PYTHON_STRICT`
          - ``1.0.0``
          - ``1.0.0b0``
          - ``1.0.0post0``
          - ``1.0.0b0.post0``
        * - :attr:`~TagFormat.PYTHON_SEMVER`
          - ``1.0.0``
          - ``1.0.0-beta0``
          - ``1.0.0-post0``
          - ``1.0.0-beta0.post0``

    """

    #: Semantic versioning, as per `semver 2.0 specification`__.
    #:
    #: __ https://semver.org/
    SEMVER = "semver"

    #: Semantic versioning with stricter constraints.
    #:
    #: Versions must contain exactly three components (i.e. ``1.0`` is not valid,
    #: ``1.0.0`` is valid.) Only ``alpha``, ``beta``, and ``rc`` keywords
    #: followed by a number are allowed in pre-release section.
    #:
    #: This schema ensures that all versions and tags are normalized
    #: and can be checked for equality without parsing them.
    SEMVER_STRICT = "semver-strict"

    #: Python versioning specification, as per `PyPA specification`__.
    #:
    #: __ https://packaging.python.org/en/latest/discussions/versioning/
    PYTHON = "python"

    #: Python versioning specification with stricter constraints.
    #:
    #: Versions must contain exactly three components (i.e. ``1.0`` is not valid,
    #: ``1.0.0`` is valid.) Leading zeroes are not allowed. Pre- and post-release
    #: parts must not be separated by point or dash, and only ``a``, ``b``,
    #: ``rc`` or ``post`` keywords are allowed.
    #:
    #: This schema ensures that all versions and tags are normalized
    #: and can be checked for equality without parsing them.
    PYTHON_STRICT = "python-strict"

    #: Python versioning specification using :attr:`~TagFormat.SEMVER_STRICT` syntax.
    #:
    #: This schema ensures that that all versions and tags are normalized,
    #: and other tools that rely on semver specification can work with them.
    #:
    #: .. note::
    #:
    #:    Semver 2.0 doesn't specify post-release semantics. As such, we use Python's
    #:    semantics and syntax: ``1.0.0-post0``, ``1.0.0-rc1.post2``, etc.
    #:
    #:    This tool will sort post-releases after actual releases, while other tools
    #:    might not work this way.
    PYTHON_SEMVER = "python-semver"

    #: No versioning semantics are implied.
    #:
    #: Automatic sorting of releases is disabled. Canonization of versions when
    #: searching for release of merging duplicate releases is also disabled.
    NONE = "none"


class GlobalConfig(yuio.config.Config):
    #: override default path to config
    config_path: pathlib.Path | None = None

    #: path to the changelog file
    file: pathlib.Path | None = None

    #: increase severity of all messages by one level
    strict: bool = False


class Config(yuio.config.Config):
    #: path to the changelog file.
    file: pathlib.Path = yuio.config.field(
        default=pathlib.Path("CHANGELOG.md"),
        parser=yuio.parse.ExistingPath(),
    )

    #: max line width for wrapping markdown files.
    format_wrapping: _t.Annotated[int, yuio.parse.Gt(0)] | Wrapping = 90

    #: ordering and titles for change categories.
    change_categories: dict[str, str] = {
        "security": "Security",
        "breaking": "Breaking",
        "added": "Added",
        "changed": "Changed",
        "deprecated": "Deprecated",
        "removed": "Removed",
        "performance": "Performance",
        "fixed": "Fixed",
    }

    #: if these change categories appear in unreleased section, suggest bumping
    #: the patch version component.
    bump_patch_categories: set[str] = {
        "security",
        "deprecated",
        "performance",
        "fixed",
    }

    #: additional items that will be added to `bump_patch_categories`
    #: without overriding it.
    extra_bump_patch_categories: set[str] = yuio.app.field(
        default=set(), merge=lambda l, r: l | r
    )

    #: if these change categories appear in unreleased section, suggest bumping
    #: the minor version component.
    bump_minor_categories: set[str] = {
        "added",
        "changed",
        "removed",
    }

    #: additional items that will be added to `bump_minor_categories`
    #: without overriding it.
    extra_bump_minor_categories: set[str] = yuio.app.field(
        default=set(), merge=lambda l, r: l | r
    )

    #: if these change categories appear in unreleased section, suggest bumping
    #: the major version component.
    bump_major_categories: set[str] = {
        "breaking",
    }

    #: additional items that will be added to `bump_major_categories`
    #: without overriding it.
    extra_bump_major_categories: set[str] = yuio.app.field(
        default=set(), merge=lambda l, r: l | r
    )

    #: additional items that will be added to `change_categories`
    #: without overriding it.
    extra_change_categories: dict[str, str] = yuio.app.field(
        default={},
        merge=lambda l, r: {**l, **r},
    )

    #: regular expressions used to normalize change categories.
    change_categories_map: dict[str, str] = {
        r"(?im)^\s*(\[\s*)?Security(\b)": "security",
        r"(?im)^\s*(\[\s*)?Break(ing|s)?(\b)": "breaking",
        r"(?im)^\s*(\[\s*)?Add(ed|s)?(\b)": "added",
        r"(?im)^\s*(\[\s*)?Change(d|s)?(\b)": "changed",
        r"(?im)^\s*(\[\s*)?Deprecate(d|s)?(\b)": "deprecated",
        r"(?im)^\s*(\[\s*)?Remove(d|s)?(\b)": "removed",
        r"(?im)^\s*(\[\s*)?Performance(\b)": "performance",
        r"(?im)^\s*(\[\s*)?Fix(ed|es)?(\b)": "fixed",
    }

    #: additional items that will be added to `change_categories_map`
    #: without overriding it.
    extra_change_categories_map: dict[str, str] = yuio.app.field(
        default={},
        merge=lambda l, r: {**l, **r},
    )

    #: name for the `unreleased` section of the changelog.
    unreleased_name: str = "Unreleased"

    #: symbols that will be added around unreleased section heading.
    unreleased_decorations: tuple[str, str] = ("", "")

    #: regular expression used to normalize unreleased changes title.
    unreleased_pattern: str = r"(?i)unreleased"

    #: symbols that will be added around each release heading.
    release_decorations: tuple[str, str] = ("", "")

    #: symbols that will be added around release date.
    release_date_decorations: tuple[str, str] = (" - ", "")

    #: symbols that will be added around release version.
    version_decorations: tuple[str, str] = ("", "")

    #: symbols that will be added around release comment.
    release_comment_decorations: tuple[str, str] = (" - ", "")

    #: whether changelog entries should have a release date in their headings.
    add_release_date: bool = True

    #: whether changelog entries should have a link to the tag attached.
    add_release_link: bool = True

    #: preset for release link templates.
    release_link_preset: ReleaseLinkPreset | None = None

    #: template for a release link, formatted using Python's `format` method.
    release_link_template: str | None = None

    #: template for a link for an unreleased entry, formatted using Python's `format` method.
    release_link_template_last: str | None = None

    #: template for a link for a first release, formatted using Python's `format` method.
    release_link_template_first: str | None = None

    #: additional variables that will be available in release link templates.
    release_link_template_vars: dict[str, str] | None = None

    #: scan git repo tags and ensure that changelog doesn't miss any release.
    check_repo_tags: bool = True

    #: prefix for release tags.
    tag_prefix: str = "v"

    #: versioning schema used to parse and sort tags.
    version_format: TagFormat = TagFormat.SEMVER

    #: don't complain about missing releases for tags before this one.
    ignore_missing_releases_before: str | None = None

    #: don't complain about missing releases if version matches this regexp.
    ignore_missing_releases_regexp: str | None = r"(?i)dev|b|beta|a|alpha|rc|post"

    #: override issue severities.
    severity: dict[
        IssueCode,
        _t.Annotated[IssueSeverity, yuio.parse.Enum(by_name=True)],
    ] = yuio.config.field(
        default={},
        merge=lambda l, r: {**l, **r},
    )

    @functools.cached_property
    def full_change_categories(self):
        full_change_categories = self.change_categories.copy()
        full_change_categories.update(self.extra_change_categories)
        return full_change_categories

    @functools.cached_property
    def full_change_categories_map(self):
        full_change_categories_map = self.change_categories_map.copy()
        full_change_categories_map.update(self.extra_change_categories_map)
        return full_change_categories_map

    @functools.cached_property
    def change_categories_sort_keys(self):
        return {k: i for i, k in enumerate(self.full_change_categories)}

    @functools.cached_property
    def parsed_ignore_missing_releases_before(self):
        from changelog_keeper.parse import parse_version

        if self.ignore_missing_releases_before is None:
            return None
        else:
            return parse_version(self.ignore_missing_releases_before, self)

    @functools.cached_property
    def full_bump_patch_categories(self):
        return self.bump_patch_categories | self.extra_bump_patch_categories

    @functools.cached_property
    def full_bump_minor_categories(self):
        return self.bump_minor_categories | self.extra_bump_minor_categories

    @functools.cached_property
    def full_bump_major_categories(self):
        return self.bump_major_categories | self.extra_bump_major_categories

    def validate_config(self):
        if self.release_link_template_vars:
            for var in ["prev_tag", "tag"]:
                if var in self.release_link_template_vars:
                    raise yuio.parse.ParsingError(
                        f"release_link_template_vars can't contain key {var!r}",
                    )
        for categories, name in [
            (self.full_change_categories_map.values(), "change_categories_map"),
            (self.full_bump_patch_categories, "bump_patch_categories"),
            (self.full_bump_minor_categories, "bump_minor_categories"),
            (self.full_bump_major_categories, "bump_major_categories"),
        ]:
            for category in categories:
                if category not in self.full_change_categories:
                    raise yuio.parse.ParsingError(
                        f"{name} has an entry for category {category}, "
                        f"which is missing from change_categories. Please add {category} "
                        "to change_categories",
                    )

        if (
            self.ignore_missing_releases_before is not None
            and self.parsed_ignore_missing_releases_before is None
        ):
            raise yuio.parse.ParsingError(
                "ignore_missing_releases_before doesn't follow"
                f" {self.version_format.value} specification",
            )


#: Default config that's used when `pyproject.toml` is detected.
PYTHON_PRESET = Config(version_format=TagFormat.PYTHON)
