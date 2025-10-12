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

    #: Error that should always result in non-zero exit code.
    CRITICAL = 4

    #: Error.
    ERROR = 3

    #: Warning.
    WARNING = 2

    #: Weak warning.
    WEAK_WARNING = 1

    #: Info.
    INFO = 1

    #: Not displayed.
    NONE = 0


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
    SEMVER = "semver"
    PYTHON = "python"


class GlobalConfig(yuio.config.Config):
    #: override default path to config
    config_path: pathlib.Path | None = yuio.app.field(
        default=None,
        parser=yuio.parse.Optional(yuio.parse.ExistingPath(extensions=[".toml"])),
        flags=["--config", "-c"],
    )

    #: increase severity of all messages by one level
    strict: bool = False

    #: increase severity of all messages by two levels
    stricter: bool = False


class Config(GlobalConfig):
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

    #: allow change categories not listed in `change_categories_map`.
    allow_unknown_change_categories: bool = False

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

    #: allowed prefixes for release tags.
    tag_prefix: str = "v"

    #: versioning schema used to parse and sort tags.
    version_format: TagFormat = TagFormat.SEMVER

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

    @property
    def strictness(self):
        if self.stricter:
            return 2
        elif self.strict:
            return 1
        else:
            return 0

    def validate_config(self):
        if self.release_link_template_vars:
            for var in ["prev_tag", "tag"]:
                if var in self.release_link_template_vars:
                    raise yuio.parse.ParsingError(
                        f"release_link_template_vars can't contain key {var!r}.",
                    )
        for category in self.full_change_categories_map.values():
            if category not in self.full_change_categories:
                raise yuio.parse.ParsingError(
                    f"full_change_categories_map has an entry for category {category}, "
                    f"which is missing from full_change_categories. Please add {category} "
                    "to full_change_categories",
                )


#: Default config that's used when `pyproject.toml` is detected.
PYTHON_PRESET = Config(version_format=TagFormat.PYTHON)
