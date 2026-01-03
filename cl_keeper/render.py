import difflib
import pathlib

import yuio.io
from markdown_it.token import Token

from cl_keeper.config import Input, Wrapping
from cl_keeper.context import Context
from cl_keeper.model import Changelog


def render(
    changelog: Changelog,
    ctx: Context,
    tokens: list[Token] | None = None,
    disable_wrapping: bool = False,
) -> str:
    if tokens is None:
        tokens = changelog.to_tokens()
    parser = changelog.parser
    if disable_wrapping:
        parser.options["mdformat"]["wrap"] = "no"
    elif isinstance(ctx.config.format_wrapping, Wrapping):
        parser.options["mdformat"]["wrap"] = ctx.config.format_wrapping.value
    else:
        parser.options["mdformat"]["wrap"] = ctx.config.format_wrapping
    parser.options["mdformat"]["number"] = True
    rendered = parser.renderer.render(tokens, parser.options, changelog.parser_env)
    return parser.render(rendered)


def print_diff(l: str, r: str, path: pathlib.Path | Input | str):
    if path is Input.STDIN:
        fromfile = "stdin"
        tofile = "stdout"
    else:
        fromfile = f"{path}:before"
        tofile = f"{path}:after"

    diff = "".join(
        difflib.unified_diff(
            l.splitlines(keepends=True),
            r.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )

    yuio.io.heading("Diff")

    if not diff:
        yuio.io.success("Diff is empty")
    else:
        yuio.io.hl(diff, syntax="diff")
