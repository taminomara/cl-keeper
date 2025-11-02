from __future__ import annotations

import typing as _t

from cl_keeper.model import Section, SubSection
from cl_keeper.typing import Ord
from markdown_it.tree import SyntaxTreeNode


def sorted_sections(sections: _t.Iterable[Section]) -> list[Section]:
    """
    Sort sections by their release version.

    """

    return sorted_by_key(sections, _sections_key, reverse=True)


def sorted_subsections(subsections: _t.Iterable[SubSection]):
    """
    Sort subsections by their preferred order.

    """

    return sorted_by_key(subsections, lambda s: s.sort_key)


def sorted_items(items: _t.Iterable[SyntaxTreeNode]):
    """
    Sort list items by their preferred order.

    """

    return sorted_by_key(items, lambda s: s.meta.get("cl_sort_key"))


def _sections_key(section: Section):
    if section.is_unreleased():
        return (1, None)
    elif release := section.as_release():
        return (0, release.parsed_version) if release.parsed_version else None
    else:
        return None


def sorted_by_key[T, K: Ord](
    items: _t.Iterable[T], key: _t.Callable[[T], K | None], reverse: bool = False
) -> list[T]:
    """
    Sort sections or subsections by the given key. If key is not present in an item,
    try keeping its position as close to the original as possible.

    """

    orderable: list[tuple[K, int, T]] = []
    unorderable: list[tuple[int, T]] = []

    for i, item in enumerate(items):
        if (k := key(item)) is not None:
            orderable.append((k, i, item))
        else:
            unorderable.append((i, item))

    orderable.sort(key=lambda x: x[0], reverse=reverse)

    if not unorderable:
        return [v for _, _, v in orderable]
    elif not orderable:
        return [v for _, v in unorderable]

    # Merge ordered and unordered items based on their position in the source.
    # Note: we don't use actual line numbers, because generated items don't have them.
    # Instead, we use indices from the original sequence.
    result: list[T] = []
    i, j = 0, 0
    while i < len(orderable) or j < len(unorderable):
        left = right = None
        left_pos = right_pos = None
        if i < len(orderable):
            _, left_pos, left = orderable[i]
        if j < len(unorderable):
            right_pos, right = unorderable[j]
        if (
            left is not None
            and left_pos is not None
            and right is not None
            and right_pos is not None
        ):
            if left_pos <= right_pos:
                result.append(left)
                i += 1
            else:
                result.append(right)
                j += 1
        elif left:
            result.append(left)
            i += 1
        elif right:
            result.append(right)
            j += 1

    return result


def merge_sections(lhs: Section, rhs: Section):
    """
    Merge content of the right section into the left section.

    """

    subsections: dict[str, SubSection] = {}
    for section in lhs, rhs:
        for subsection in section.subsections:
            if subsection.category in subsections:
                merge_subsections(subsections[subsection.category], subsection)
            else:
                subsections[subsection.category] = subsection
    lhs.subsections = list(subsections.values())


def merge_subsections(lhs: SubSection, rhs: SubSection):
    """
    Merge content of the right subsection into the left subsection.

    """

    if (
        lhs.content
        and rhs.content
        and lhs.content[-1].type in ["bullet_list", "ordered_list"]
        and rhs.content[0].type == lhs.content[-1].type
    ):
        lhs.content[-1].children += rhs.content[0].children
        lhs.content[-1].meta["cl_is_changelist"] = lhs.content[-1].meta.get(
            "cl_is_changelist", False
        ) or rhs.content[0].meta.get("cl_is_changelist", False)
        lhs.content += rhs.content[1:]
    else:
        lhs.content += rhs.content
