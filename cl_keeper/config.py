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
    """
    Disable wrapping, print all paragraphs in a single line.

    """

    KEEP = "keep"
    """
    Keep the original file wrapping.

    """


class IssueSeverity(enum.Enum):
    """
    Severity of the issue.

    """

    ERROR = 4
    """
    Error.

    """

    WARNING = 3
    """
    Warning.

    """

    WEAK_WARNING = 2
    """
    Weak warning.

    """

    INFO = 1
    """
    Info.

    """

    NONE = 0
    """
    Not displayed.

    """


class IssueCode(enum.Enum):
    GENERAL_FORMATTING_ERROR = "GeneralFormattingError"
    """
    A formatting error related to the general structure of the changelog.

    """

    INVALID_VERSION = "InvalidVersion"
    """
    Release version doesn't follow the requested specification.

    """

    INVALID_TAG = "InvalidTag"
    """
    Tag format doesn't follow the requested versioning specification.

    To disable all repository checks, set :attr:`~Config.check_repo_tags` to ``False``.
    """

    MISSING_RELEASE_FOR_TAG = "MissingReleaseForTag"
    """
    Found a tag that has no associated release.

    To suppress this error for all versions before the given one,
    set `ignore_missing_releases_before`. To disable all repository checks,
    set :attr:`~Config.check_repo_tags` to ``False``.

    """

    MISSING_TAG_FOR_RELEASE = "MissingTagForRelease"
    """
    Found a release that has no associated tag in the repository.

    To disable all repository checks, set :attr:`~Config.check_repo_tags` to ``False``.

    """

    RELEASE_ORDERING = "ReleaseOrdering"
    """
    Releases are not ordered according to their versions.

    Releases are compared according to the chosen versioning specification.

    """

    UNRELEASED_HEADING_FORMAT = "UnreleasedHeadingFormat"
    """
    Heading for unreleased changes doesn't meet formatting requirements.

    Heading format is controlled by `unreleased_name`.

    """

    RELEASE_HEADING_FORMAT = "ReleaseHeadingFormat"
    """
    Heading for a release doesn't meet formatting requirements.

    """

    INVALID_RELEASE_DATE = "InvalidReleaseDate"
    """
    Release date can't be parsed.

    This usually indicates that the release date is incorrect. For example,
    it refers to a day that doesn't exist in the calendar.

    """

    MISSING_RELEASE_DATE = "MissingReleaseDate"
    """
    Release date is missing.

    :attr:`~Config.add_release_date` is ``True``, but release date is missing.

    """

    UNEXPECTED_RELEASE_DATE = "UnexpectedReleaseDate"
    """
    Release date should not be present.

    :attr:`~Config.add_release_date` is ``False``, but release date is present.

    """

    MISSING_RELEASE_LINK = "MissingReleaseLink"
    """
    Release link is missing.

    :attr:`~Config.add_release_link` is ``True``, but release link is missing.

    """

    UNEXPECTED_RELEASE_LINK = "UnexpectedReleaseLink"
    """
    Release link should not be present.

    :attr:`~Config.add_release_link` is ``False``, but release link is present.

    """

    INCORRECT_RELEASE_DATE = "IncorrectReleaseDate"
    """
    Release date doesn't match date of the release commit.

    To disable all repository checks, set :attr:`~Config.check_repo_tags` to ``False``.

    """

    INCORRECT_RELEASE_LINK = "IncorrectReleaseLink"
    """
    Release link is incorrect.

    Release links are generated using `release_link_preset`
    and `release_link_template`. We use order of releases from the changelog
    to generate links for commit ranges.

    """

    DUPLICATE_RELEASES = "DuplicateReleases"
    """
    Found multiple releases for the same version.

    """

    EMPTY_RELEASE = "EmptyRelease"
    """
    Section for a release is empty.

    To ignore empty sections prior to some version,
    set `ignore_missing_releases_before`.

    """

    CHANGE_CATEGORY_ORDERING = "ChangeCategoryOrdering"
    """
    Order of sub-sections within a release doesn't match
    the one given in `change_categories`.

    """

    CHANGE_CATEGORY_HEADING_FORMAT = "ChangeCategoryHeadingFormat"
    """
    Heading for a change category doesn't meet formatting requirements.

    """

    UNKNOWN_CHANGE_CATEGORY = "UnknownChangeCategory"
    """
    Heading for a change category doesn't appear in `change_categories_map`.

    """

    DUPLICATE_CHANGE_CATEGORIES = "DuplicateChangeCategories"
    """
    Found multiple release sub-sections with the same title.

    """

    EMPTY_CHANGE_CATEGORY = "EmptyChangeCategory"
    """
    Found a release sub-section without content.

    """

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

    def update_vars(self, vars: dict[str, str], override: bool = False):
        if override:
            self.vars.update(vars)
        else:
            for k, v in vars.items():
                self.vars.setdefault(k, v)
        return self


class ReleaseLinkPreset(enum.Enum):
    GITHUB = "github"
    """
    Will link releases to tags on github.

    To use this preset, add the ``repo`` template variable
    to :attr:`~Config.release_link_template_vars`.
    It should contain url of your repository.

    If you're using self-hosted GitHub, you can also add the ``host``
    template variable.

    **Example configuration:**

    .. code-block:: yaml

        release_link_preset: github
        release_link_template_vars:
            repo: "taminomara/cl-keeper"

    """

    GITLAB = "gitlab"
    """
    Will link releases to tags on gitlab.

    To use this preset, add the ``repo`` template variable
    to :attr:`~Config.release_link_template_vars`.
    It should contain url of your repository.

    If you're using self-hosted GitLab, you can also add the ``host``
    template variable.

    **Example configuration:**

    .. code-block:: yaml

        release_link_preset: gitlab
        release_link_template_vars:
            repo: "taminomara/cl-keeper"

    """

    NONE = "none"
    """
    Will not generate links automatically.

    """

    def get_links(self) -> LinkTemplates:
        match self:
            case ReleaseLinkPreset.GITHUB:
                return LinkTemplates(
                    "https://{host}/{repo}/compare/{prev_tag}...{tag}",
                    "https://{host}/{repo}/compare/{prev_tag}...HEAD",
                    "https://{host}/{repo}/releases/tag/{tag}",
                    {"host": "github.com"},
                )
            case ReleaseLinkPreset.GITLAB:
                return LinkTemplates(
                    "https://{host}/{repo}/-/compare/{prev_tag}...{tag}",
                    "https://{host}/{repo}/-/compare/{prev_tag}...HEAD",
                    "https://{host}/{repo}/-/tags/{tag}",
                    {"host": "gitlab.com"},
                )
            case ReleaseLinkPreset.NONE:
                return LinkTemplates("", "", "", {})


class VersionFormat(enum.Enum):
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

        * - :attr:`~VersionFormat.SEMVER`
          - ``1.0.0``
          - ``1.0.0-b``, ``1.0.0-b0``, ``1.0.0-beta0``, etc.
          - not supported
          - not supported
        * - :attr:`~VersionFormat.SEMVER_STRICT`
          - ``1.0.0``
          - ``1.0.0-beta0``
          - not supported
          - not supported
        * - :attr:`~VersionFormat.PYTHON`
          - ``1.0.0``
          - ``1.0.0b0``, ``1.0.0-beta.0``, etc.
          - ``1.0.0post0``, ``1.0.0-rev.0``, etc.
          - ``1.0.0b1.post2``, ``1.0.0-beta.1post2``, etc.
        * - :attr:`~VersionFormat.PYTHON_STRICT`
          - ``1.0.0``
          - ``1.0.0b0``
          - ``1.0.0post0``
          - ``1.0.0b0.post0``
        * - :attr:`~VersionFormat.PYTHON_SEMVER`
          - ``1.0.0``
          - ``1.0.0-beta0``
          - ``1.0.0-post0``
          - ``1.0.0-beta0.post0``

    """

    SEMVER = "semver"
    """
    Semantic versioning, as per `semver 2.0 specification`__.

    __ https://semver.org/

    """

    SEMVER_STRICT = "semver-strict"
    """
    Semantic versioning with stricter constraints.

    Versions must contain exactly three components (i.e. ``1.0`` is not valid,
    ``1.0.0`` is valid.) Only ``alpha``, ``beta``, and ``rc`` keywords
    followed by a number are allowed in pre-release section.

    This schema ensures that all versions and tags are normalized
    and can be checked for equality without parsing them.

    """

    PYTHON = "python"
    """
    Python versioning specification, as per `PyPA specification`__.

    __ https://packaging.python.org/en/latest/discussions/versioning/

    """

    PYTHON_STRICT = "python-strict"
    """
    Python versioning specification with stricter constraints.

    Versions must contain exactly three components (i.e. ``1.0`` is not valid,
    ``1.0.0`` is valid.) Leading zeroes are not allowed. Pre- release
    part must not be separated by point or dash, and only ``a``, ``b``,
    ``rc`` or ``post`` keywords are allowed.

    This schema ensures that all versions and tags are normalized
    and can be checked for equality without parsing them.

    """

    PYTHON_SEMVER = "python-semver"
    """
    Python versioning specification using :attr:`~VersionFormat.SEMVER_STRICT` syntax.

    This schema ensures that that all versions and tags are normalized,
    and other tools that rely on semver specification can work with them.

    .. note::

       Semver 2.0 doesn't specify post-release semantics. As such, we use Python's
       semantics and syntax: ``1.0.0-post0``, ``1.0.0-rc1.post2``, etc.

       This tool will sort post-releases after actual releases, while other tools
       might not work this way.

    """

    NONE = "none"
    """
    No versioning semantics are implied.

    Automatic sorting of releases is disabled. Canonization of versions when
    searching for release of merging duplicate releases is also disabled.

    """


class GlobalConfig(yuio.config.Config):
    config_path: pathlib.Path | None = None
    """
    Override default path to config.

    """

    file: pathlib.Path | None = None
    """
    Path to the changelog file.

    """

    strict: bool = False
    """
    Increase severity of all messages by one level.

    """


class Config(yuio.config.Config):
    file: pathlib.Path = yuio.config.field(
        default=pathlib.Path("CHANGELOG.md"),
        parser=yuio.parse.ExistingPath(),
        flags=yuio.DISABLED,
    )
    """
    Path to the changelog file, relative to this config location.

    """

    format_wrapping: (
        _t.Annotated[int, yuio.parse.Gt(0)]
        | _t.Annotated[Wrapping, yuio.parse.Enum(doc_inline=True)]
    ) = yuio.config.field(
        default=90,
        help="max line width for wrapping markdown files",
    )
    """
    Max line width for wrapping markdown files.

    Can be a positive number, a string ``no``, or a string ``keep``. ``no`` will
    format all paragraphs in a single line, while ``keep`` will preserve the original
    wrapping.

    """

    change_categories: dict[str, str] = yuio.config.field(
        default={
            "security": "Security",
            "breaking": "Breaking",
            "added": "Added",
            "changed": "Changed",
            "deprecated": "Deprecated",
            "removed": "Removed",
            "performance": "Performance",
            "fixed": "Fixed",
        },
        help="ordering and titles for change categories",
    )
    """
    Ordering and titles for change categories.

    This config item defines known change categories (i.e. third level headings
    in release section, such as "Added" or "Changed").

    Its keys are category names used in other config items to refer to sections.

    Its values are category titles that will be used in section headings.
    If a value is empty, section's heading will not be replaced.

    Order of elements defines the preferred order of sections in the changelog.

    By default, changelog keeper defines the following sections:

    .. list-table::
        :header-rows: 1

        * - Category
          - Title
        * - ``security``
          - Security
        * - ``breaking``
          - Breaking
        * - ``added``
          - Added
        * - ``changed``
          - Changed
        * - ``deprecated``
          - Deprecated
        * - ``removed``
          - Removed
        * - ``performance``
          - Performance
        * - ``fixed``
          - Fixed

    :meta value: ...

    """

    extra_change_categories: dict[str, str] = yuio.app.field(
        default={},
        merge=lambda l, r: {**l, **r},
        help=(
            "additional items that will be added to `--cfg-change-categories` "
            "without completely overriding it"
        ),
    )
    """
    Additional items that will be added to :attr:`~Config.change_categories`
    without completely overriding it.

    """

    bump_patch_categories: set[str] = yuio.app.field(
        default={
            "security",
            "deprecated",
            "performance",
            "fixed",
        },
        help=(
            "if these change categories appear in unreleased section, "
            "suggest bumping the patch version component."
        ),
    )
    """
    If these change categories appear in unreleased section, suggest bumping
    the patch version component.

    Default is ``security``, ``deprecated``, ``performance``, ``fixed``.

    :meta value: ...

    """

    extra_bump_patch_categories: set[str] = yuio.app.field(
        default=set(),
        merge=lambda l, r: l | r,
        help=(
            "additional items that will be added to `--cfg-bump-patch-categories` "
            "without completely overriding it"
        ),
    )
    """
    Additional items that will be added to :attr:`~Config.bump_patch_categories`
    without completely overriding it.

    """

    bump_minor_categories: set[str] = yuio.app.field(
        default={
            "added",
            "changed",
            "removed",
        },
        help=(
            "if these change categories appear in unreleased section, "
            "suggest bumping the minor version component."
        ),
    )
    """
    If these change categories appear in unreleased section, suggest bumping
    the minor version component.

    Default is ``added``, ``changed``, ``removed``.

    :meta value: ...

    """

    extra_bump_minor_categories: set[str] = yuio.app.field(
        default=set(),
        merge=lambda l, r: l | r,
        help=(
            "additional items that will be added to `--cfg-bump-minor-categories` "
            "without completely overriding it"
        ),
    )
    """
    Additional items that will be added to :attr:`~Config.bump_minor_categories`
    without completely overriding it.

    """

    bump_major_categories: set[str] = yuio.app.field(
        default={
            "breaking",
        },
        help=(
            "if these change categories appear in unreleased section, "
            "suggest bumping the major version component."
        ),
    )
    """
    If these change categories appear in unreleased section, suggest bumping
    the major version component.

    Default is ``breaking``.

    :meta value: ...

    """

    extra_bump_major_categories: set[str] = yuio.app.field(
        default=set(),
        merge=lambda l, r: l | r,
        help=(
            "additional items that will be added to `--cfg-bump-major-categories` "
            "without completely overriding it"
        ),
    )
    """
    Additional items that will be added to :attr:`~Config.bump_major_categories`
    without completely overriding it.

    """

    change_categories_map: dict[str, str] = yuio.app.field(
        default={
            r"(?im)\bsecurity\b": "security",
            r"(?im)\bbreak(ing|s)?\b": "breaking",
            r"(?im)\badd(ed|s)?\b": "added",
            r"(?im)\bchange(d|s)?\b": "changed",
            r"(?im)\bdeprecate(d|s)?\b": "deprecated",
            r"(?im)\bremove(d|s)?\b": "removed",
            r"(?im)\bperformance\b": "performance",
            r"(?im)\bfix(ed|es)?\b": "fixed",
        },
        help=(
            "a mapping from regular expressions to change category names, "
            "used to parse and normalize categories"
        ),
    )
    r"""
    A mapping from regular expressions to change category names, used to parse
    and normalize categories.

    When processing a release, each third level heading will be matched against
    these regular expressions to figure out which section it represents. If there
    is a match, the heading content will be replaced by the one from
    :attr:`~Config.change_categories`, and the section will be reordered to match
    the order from :attr:`~Config.change_categories`.

    Regular expression syntax is described in the :mod:`re` module documentation.
    Regular expressions will be compiled without flags, but you can use inline
    flags to enable case-insensitivity.

    :meta value: ...

    """

    extra_change_categories_map: dict[str, str] = yuio.app.field(
        default={},
        merge=lambda l, r: {**l, **r},
        help=(
            "additional items that will be added to `--cfg-change-categories-map` "
            "without completely overriding it"
        ),
    )
    """
    Additional items that will be added to :attr:`~Config.change_categories_map`
    without completely overriding it.

    """

    unreleased_name: str = yuio.app.field(
        default="Unreleased",
        help="title for the `unreleased` section of the changelog",
    )
    """
    Title for the ``unreleased`` section of the changelog.

    """

    unreleased_decorations: tuple[str, str] = yuio.app.field(
        default=("", ""),
        help="symbols that will be added around unreleased heading",
    )
    """
    Symbols that will be added around :attr:`~Config.unreleased_name`, but won't
    be turned into a link.

    This value should be a tuple of two strings, first will be placed before the title,
    second will be placed after.

    """

    unreleased_pattern: str = yuio.app.field(
        default=r"(?i)unreleased",
        help="regular expression used to detect sections with unreleased changes",
    )
    """
    Regular expression used to detect sections with unreleased changes.

    """

    release_decorations: tuple[str, str] = yuio.app.field(
        default=("", ""),
        help="symbols that will be added around each release heading",
    )
    """
    Symbols that will be added around each release heading.

    """

    release_date_decorations: tuple[str, str] = yuio.app.field(
        default=(" - ", ""),
        help="symbols that will be added around release date",
    )
    """
    Symbols that will be added around release date.

    """

    version_decorations: tuple[str, str] = yuio.app.field(
        default=("", ""),
        help="symbols that will be added around release version",
    )
    """
    Symbols that will be added around release version.

    """

    release_comment_decorations: tuple[str, str] = yuio.app.field(
        default=(" - ", ""),
        help="symbols that will be added around release comments",
    )
    """
    Symbols that will be added around release comments.

    """

    add_release_date: bool = yuio.app.field(
        default=True,
        help="whether changelog entries should have a release date in their headings",
    )
    """
    Whether changelog entries should have a release date in their headings.

    """

    add_release_link: bool = yuio.app.field(
        default=True,
        help=(
            "whether changelog entries should have links to tags/diffs in their headings"
        ),
    )
    """
    Whether changelog entries should have links to tags/diffs in their headings.

    """

    release_link_preset: ReleaseLinkPreset | None = yuio.app.field(
        default=None,
        help="preset for release link templates",
    )
    """
    Preset for release link templates.

    By default, a correct preset is inferred by inspecting repository's remotes.
    If this process fails, you can configure a preset manually.

    """

    release_link_template: str | None = yuio.app.field(
        default=None,
        help=(
            "template for a release link, "
            "formatted using Python's `str.format` method"
        ),
    )
    """
    Template for a release link, formatted using Python's :meth:`str.format` method.
    This setting overrides link from :attr:`preset <Config.release_link_preset>`.

    The following template variables are available, in addition to
    ones declared in :attr:`~Config.release_link_template_vars`:

    ``tag``
        Git tag for the current release.

    ``prev_tag``
        Git tag for the previous release.

    **Example:**

    .. code-block:: yaml

        release_link_template: "https://{host}/{repo}/compare/{prev_tag}...{tag}"
        release_link_template_vars:
            host: "github.com"
            repo: "taminomara/cl-keeper"

    """

    release_link_template_last: str | None = yuio.app.field(
        default=None,
        help=(
            "template for a link for an unreleased entry, "
            "formatted using Python's `str.format` method"
        ),
    )
    """
    Template for a link for an unreleased entry, formatted using
    Python's :meth:`str.format` method. This setting overrides link from
    :attr:`preset <Config.release_link_preset>`.

    The following template variables are available, in addition to
    ones declared in :attr:`~Config.release_link_template_vars`:

    ``prev_tag``
        Git tag for the latest release.

    **Example:**

    .. code-block:: yaml

        release_link_template_last: "https://{host}/{repo}/compare/{prev_tag}...HEAD"
        release_link_template_vars:
            host: "github.com"
            repo: "taminomara/cl-keeper"

    """

    release_link_template_first: str | None = yuio.app.field(
        default=None,
        help=(
            "template for a link for the first release, "
            "formatted using Python's `str.format` method"
        ),
    )
    """
    Template for a link for the first release, formatted using
    Python's :meth:`str.format` method. This setting overrides link from
    :attr:`preset <Config.release_link_preset>`.

    The following template variables are available, in addition to
    ones declared in :attr:`~Config.release_link_template_vars`:

    ``tag``
        Git tag for the current release.

    **Example:**

    .. code-block:: yaml

        release_link_template_first: "https://{host}/{repo}/releases/tag/{tag}"
        release_link_template_vars:
            host: "github.com"
            repo: "taminomara/cl-keeper"

    """

    release_link_template_vars: dict[str, str] | None = yuio.app.field(
        default=None,
        help=("additional variables that will be available in release link templates"),
    )
    """
    Additional variables that will be available in release link templates.

    """

    check_repo_tags: bool = yuio.app.field(
        default=True,
        help="scan git repo and ensure that changelog doesn't miss any release",
    )
    """
    Scan git repo and ensure that changelog doesn't miss any release.

    Default is ``true``.

    """

    tag_prefix: str = yuio.app.field(
        default="v",
        help="prefix for release tags",
    )
    """
    Prefix for release tags.

    Only tags that start with this prefix are considered release tags.

    Default is ``"v"``.

    """

    version_format: VersionFormat = yuio.app.field(
        default=VersionFormat.SEMVER,
        help="versioning schema used to parse and sort tags and versions",
    )
    """
    Versioning schema used to parse and sort tags and versions.

    See :class:`VersionFormat` for details.

    """

    ignore_missing_releases_before: str | None = yuio.app.field(
        default=None,
        help="don't complain about missing releases for tags before this one",
    )
    """
    Don't complain about missing releases for tags before this one.

    """

    ignore_missing_releases_regexp: str | None = yuio.app.field(
        default=r"(?i)dev|b|beta|a|alpha|rc|post",
        help="don't complain about missing releases if version matches this regexp",
    )
    """
    Don't complain about missing releases if version matches this regexp.

    Default regexp searches for the following substrings:
    ``dev|b|beta|a|alpha|rc|post``.

    """

    severity: dict[
        _t.Annotated[
            IssueCode,
            yuio.parse.WithMeta(desc="<code>"),
        ],
        _t.Annotated[
            IssueSeverity,
            yuio.parse.Enum(by_name=True, to_dash_case=True),
            yuio.parse.WithMeta(desc="<severity>"),
        ],
    ] = yuio.config.field(
        default={},
        merge=lambda l, r: {**l, **r},
        help="mapping from issue code to issue severity",
    )
    """
    A mapping from issue code to issue severity. Allows customizing and disabling
    certain checks.

    """

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
        from cl_keeper.parse import parse_version

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
            if self.version_format is VersionFormat.NONE:
                raise yuio.parse.ParsingError(
                    "ignore_missing_releases_before can't be used "
                    "with `version_format=none`",
                )
            else:
                raise yuio.parse.ParsingError(
                    "ignore_missing_releases_before doesn't follow "
                    f"{self.version_format.value} specification",
                )


PYTHON_PRESET = Config(version_format=VersionFormat.PYTHON)
"""
Default config that's used when `pyproject.toml` is detected.

"""
