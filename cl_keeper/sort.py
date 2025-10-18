from __future__ import annotations

import math
import typing as _t

from cl_keeper.model import Section, SubSection
from cl_keeper.typing import Ord, SupportsPos


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


def _sections_key(section: Section):
    if section.is_unreleased():
        return (1, None)
    elif release := section.as_release():
        return (0, release.parsed_version) if release.parsed_version else None
    else:
        return None


def sorted_by_key[T: SupportsPos, K: Ord](
    items: _t.Iterable[T], key: _t.Callable[[T], K | None], reverse: bool = False
) -> list[T]:
    """
    Sort sections or subsections by the given key. If key is not present in an item,
    try keeping its position as close to the original as possible.

    """

    orderable: list[tuple[K, T]] = []
    unorderable: list[T] = []

    for item in items:
        if (k := key(item)) is not None:
            orderable.append((k, item))
        else:
            unorderable.append(item)

    orderable.sort(key=lambda x: x[0], reverse=reverse)

    if not unorderable:
        return [v for _, v in orderable]
    elif not orderable:
        return unorderable

    # Merge ordered and unordered items based on their position in the source.
    result: list[T] = []
    i, j = 0, 0
    while i < len(orderable) or j < len(unorderable):
        left = right = None
        if i < len(orderable):
            left = orderable[i][1]
        if j < len(unorderable):
            right = unorderable[j]
        if left and right:
            left_pos = left.map or (math.inf, 0)
            right_pos = right.map or (math.inf, 0)
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

    subsections: dict[str | None, SubSection] = {}
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
        len(lhs.content) == 1
        and len(rhs.content) == 1
        and lhs.content[0].type in ["bullet_list", "ordered_list"]
        and rhs.content[0].type == lhs.content[0].type
    ):
        lhs.content[0].children += rhs.content[0].children
    else:
        lhs.content += rhs.content
