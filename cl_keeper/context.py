from __future__ import annotations

import enum
import pathlib
import typing as _t

import yuio.io

from cl_keeper.config import Config, IssueCode, IssueSeverity, LinkTemplates
from cl_keeper.typing import SupportsPos


class IssueScope(enum.Enum):
    """
    Scope where an issue happened.

    """

    #: For issues originating from environment,
    #: i.e. repository tags not being properly formatted.
    EXTERNAL = 0

    #: For issues originating from the changelog file.
    CHANGELOG = 1


#: Position of an issue, a pair of 0-based line numbers, first and last line.
IssuePosition: _t.TypeAlias = tuple[int, int]


class Context:
    def __init__(
        self,
        path: pathlib.Path,
        src: str,
        config: Config,
        strict: bool,
        link_templates: LinkTemplates,
    ) -> None:
        self.path = path
        self.src = src
        self.lines = self.src.splitlines()
        self.config = config
        self.strict = strict
        self.link_templates = link_templates
        self._has_errors = False
        self._messages: list[
            tuple[
                str,
                tuple[_t.Any, ...],
                IssuePosition | None,
                IssueCode,
                IssueScope,
                IssueSeverity,
            ]
        ] = []

    def reset(self, src: str):
        self.src = src
        self.lines = self.src.splitlines()
        self._has_errors = False
        self._messages = []

    def issue(
        self,
        code: IssueCode,
        msg: str,
        *args: _t.Any,
        pos: int | tuple[int, int] | SupportsPos | None = None,
        scope: IssueScope = IssueScope.CHANGELOG,
    ):
        severity = self.config.severity.get(code, code.default_severity())
        severity = self._up(severity)
        if severity is IssueSeverity.NONE:
            return
        if severity.value >= IssueSeverity.ERROR.value:
            self._has_errors = True
        if isinstance(pos, SupportsPos):
            pos = pos.map
        elif isinstance(pos, int):
            pos = (pos, pos + 1)
        self._messages.append((msg, args, pos, code, scope, severity))

    def report(self):
        self._messages.sort(key=lambda x: (x[3].value, -x[4].value, x[2] or (0, 0)))
        prev_pos = None
        prev_title = None
        for i, (msg, args, pos, code, _, severity) in enumerate(self._messages):
            if i >= 50:
                self._print_source(prev_pos)
                skipped = len(self._messages) - 50
                yuio.io.error(
                    "<c b>+ %s more message%s skipped.</c>",
                    skipped,
                    "" if skipped == 1 else "s",
                )
                return

            color, title = self._color_and_title(severity)
            if not color or not title:
                continue
            msg += f" [{code.value}]"
            if pos != prev_pos:
                self._print_source(prev_pos)
            if pos and (pos != prev_pos or title != prev_title):
                yuio.io.info(f"<c b>{title} on line {pos[0] + 1}:</c>", color=color)
            if pos:
                yuio.io.info("  - " + msg, *args, color=color)
            else:
                yuio.io.info(f"<c b>{title}: {msg}</c>", *args, color=color)
            prev_pos = pos
            prev_title = title
        self._print_source(prev_pos)

    def has_errors(self) -> bool:
        return self._has_errors

    def has_messages(self) -> bool:
        return bool(self._messages)

    def exit_if_has_errors(self):
        if self.has_errors():
            exit(3)

    def _print_source(self, pos: tuple[int, int] | None):
        if pos:
            for line in range(*pos):
                if line < len(self.lines):
                    yuio.io.info(
                        "  <c dim>%4d |</c> %s",
                        line + 1,
                        self.lines[line],
                    )
                else:
                    break

    def _up(self, severity: IssueSeverity) -> IssueSeverity:
        return IssueSeverity(
            min(severity.value + self.strict, IssueSeverity.ERROR.value)
        )

    @staticmethod
    def _color_and_title(severity: IssueSeverity):
        match severity:
            case IssueSeverity.ERROR:
                return "report_error", "Error"
            case IssueSeverity.WARNING:
                return "report_warning", "Warning"
            case IssueSeverity.WEAK_WARNING:
                return "report_weak_warning", "Weak warning"
            case IssueSeverity.INFO:
                return "report_info", "Info"
            case IssueSeverity.NONE:
                return None, None
