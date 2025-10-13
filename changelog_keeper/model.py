from __future__ import annotations

import dataclasses
import datetime
import enum
import typing as _t
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode


class Version:
    def __lt__(self, other: _t.Self, /) -> bool: ...
    def __le__(self, other: _t.Self, /) -> bool: ...
    def __gt__(self, other: _t.Self, /) -> bool: ...
    def __ge__(self, other: _t.Self, /) -> bool: ...
    def __eq__(self, other: object, /) -> bool: ...
    def __ne__(self, other: object, /) -> bool: ...


@dataclass(kw_only=True)
class RepoVersion:
    version: str
    parsed_version: Version | None
    canonized_version: str
    author_date: datetime.date
    committer_date: datetime.date


@dataclass(kw_only=True)
class Changelog:
    sections: list[Section]
    parser: MarkdownIt
    parser_env: dict[str, _t.Any]

    def to_tokens(self) -> list[Token]:
        return [token for section in self.sections for token in section.to_tokens()]


@dataclass(kw_only=True)
class Section:
    """
    A single section of a changelog file.

    """

    #: Section heading, can be missing for trivia sections.
    heading: SyntaxTreeNode | None

    #: Section content.
    subsections: list[SubSection]

    def what(self) -> str:
        return "trivia section"

    def is_trivia(self) -> bool:
        return not isinstance(self, (ReleaseSection, UnreleasedSection))

    def is_release(self) -> bool:
        return isinstance(self, ReleaseSection)

    def as_release(self) -> ReleaseSection | None:
        if isinstance(self, ReleaseSection):
            return self
        else:
            return None

    def is_unreleased(self) -> bool:
        return isinstance(self, UnreleasedSection)

    def as_unreleased(self) -> UnreleasedSection | None:
        if isinstance(self, UnreleasedSection):
            return self
        else:
            return None

    @property
    def map(self) -> tuple[int, int] | None:
        if self.heading and self.heading.map:
            return self.heading.map
        for child in self.subsections:
            if child.map:
                return child.map
        return None

    def to_tokens(self, include_heading: bool = True) -> list[Token]:
        tokens: list[Token] = []
        if self.heading and include_heading:
            tokens.extend(self.heading.to_tokens())
        for child in self.subsections:
            tokens.extend(child.to_tokens())
        return tokens

    def walk(self):
        if self.heading is not None:
            yield from self.heading.walk()
        for subsection in self.subsections:
            yield from subsection.walk()


@dataclass(kw_only=True)
class UnreleasedSection(Section):
    #: Link attached to version string, if there was any.
    version_link: str | None

    #: Link label attached to version string, if there was any.
    version_label: str | None

    def what(self) -> str:
        return "unreleased section"


@dataclass(kw_only=True)
class ReleaseSection(Section):
    #: Version string extracted from the heading, only set in release sections.
    version: str

    #: Parsed version suitable for ordering, can be absent if `version` failed to parse.
    parsed_version: Version | None

    #: Canonized version suitable for comparing for equality.
    canonized_version: str

    #: Link attached to version string, if there was any.
    version_link: str | None

    #: Link label attached to version string, if there was any.
    version_label: str | None

    #: Known release date, either extracted from heading or from git metadata.
    release_date: datetime.date | None

    #: Formatted release date, possible an invalid one.
    release_date_fmt: str | None

    #: Heading text that was found after release version and date.
    release_comment: str | None

    def what(self) -> str:
        return f"release `{self.version}`"


class SubSectionType(enum.Enum):
    #: Subsection that contains some text that doesn't describe changes.
    TRIVIA = "TRIVIA"

    #: Subsection that contains release changes.
    CHANGES = "CHANGES"


class SubSectionCategoryKind(enum.Enum):
    #: Subsection's category was recognized.
    KNOWN = "KNOWN"

    #: Subsection's category was not recognized.
    UNKNOWN = "UNKNOWN"


@dataclass(kw_only=True)
class SubSection:
    """
    Content of a changelog section.

    """

    #: Subsection type.
    type: SubSectionType = SubSectionType.TRIVIA

    #: Subsection heading, can be missing for trivia subsections.
    heading: SyntaxTreeNode | None = None

    #: Whether `category` was recognized as a known category. Trivia subsections
    #: are always `UNKNOWN`.
    category_kind: SubSectionCategoryKind = SubSectionCategoryKind.UNKNOWN

    #: Category of changes, recognized by scanning heading
    #: with `change_categories_map`. For `UNKNOWN` category kinds, this contains
    #: case-folded heading content for merging subsections with same headings.
    #: For trivia subsections, this contains an empty string.
    category: str = ""

    #: Index of subsection category in the canonical order of subsections.
    sort_key: int | None = None

    #: Subsection content.
    content: list[SyntaxTreeNode] = dataclasses.field(default_factory=list)

    @property
    def map(self) -> tuple[int, int] | None:
        if self.heading and self.heading.map:
            return self.heading.map
        for child in self.content:
            if child.map:
                return child.map
        return None

    def to_tokens(self) -> list[Token]:
        tokens: list[Token] = []
        if self.heading:
            tokens.extend(self.heading.to_tokens())
        for child in self.content:
            tokens.extend(child.to_tokens())
        return tokens

    def walk(self):
        for node in self.content:
            yield from node.walk()
