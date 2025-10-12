from __future__ import annotations

import abc
import typing as _t


@_t.runtime_checkable
class SupportsPos(_t.Protocol):
    @property
    @abc.abstractmethod
    def map(self) -> tuple[int, int] | None:
        """
        Return object's position in the changelog file.

        """


class Ord(_t.Protocol):
    @abc.abstractmethod
    def __lt__(self, other: _t.Self, /) -> bool: ...
