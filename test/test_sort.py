import pathlib
import textwrap
from dataclasses import dataclass

import pytest
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode

from cl_keeper.config import Config
from cl_keeper.context import Context
from cl_keeper.model import SubSection
from cl_keeper.parse import build_parser, parse
from cl_keeper.sort import merge_sections, merge_subsections, sorted_by_key


@dataclass
class Sortable:
    version: int | None
    cookie: int | None = None


@pytest.mark.parametrize(
    "args,expected",
    [
        pytest.param(
            [],
            [],
            id="empty",
        ),
        pytest.param(
            [Sortable(3), Sortable(1), Sortable(2)],
            [Sortable(1), Sortable(2), Sortable(3)],
            id="all_versioned",
        ),
        pytest.param(
            [Sortable(None, 1), Sortable(None, 2), Sortable(None, 3)],
            [Sortable(None, 1), Sortable(None, 2), Sortable(None, 3)],
            id="none_versioned",
        ),
        pytest.param(
            [Sortable(1), Sortable(None, 1), Sortable(None, 2)],
            [Sortable(1), Sortable(None, 1), Sortable(None, 2)],
            id="one_versioned_1",
        ),
        pytest.param(
            [Sortable(None, 1), Sortable(1), Sortable(None, 2)],
            [Sortable(None, 1), Sortable(1), Sortable(None, 2)],
            id="one_versioned_2",
        ),
        pytest.param(
            [Sortable(None, 1), Sortable(None, 2), Sortable(1)],
            [Sortable(None, 1), Sortable(None, 2), Sortable(1)],
            id="one_versioned_3",
        ),
        pytest.param(
            [Sortable(1), Sortable(None), Sortable(2)],
            [Sortable(1), Sortable(None), Sortable(2)],
            id="some_versioned",
        ),
        pytest.param(
            [Sortable(1), Sortable(None, 1), Sortable(2), Sortable(None, 2)],
            [Sortable(1), Sortable(None, 1), Sortable(2), Sortable(None, 2)],
            id="some_versioned_2",
        ),
        pytest.param(
            [Sortable(1), Sortable(None), Sortable(1)],
            [Sortable(1), Sortable(None), Sortable(1)],
            id="some_versioned_same_version",
        ),
        pytest.param(
            [Sortable(2), Sortable(None, 1), Sortable(1), Sortable(None, 2)],
            [Sortable(None, 1), Sortable(1), Sortable(2), Sortable(None, 2)],
            id="some_versioned_crossed",
        ),
        pytest.param(
            [Sortable(None, 1), Sortable(2), Sortable(1), Sortable(None, 2)],
            [Sortable(None, 1), Sortable(1), Sortable(2), Sortable(None, 2)],
            id="some_versioned_crossed_2",
        ),
    ],
)
def test_sort(args, expected):
    result = sorted_by_key(args, lambda x: x.version)
    assert result == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        pytest.param(
            """
            ## v1.0.0
            """,
            """
            ## v1.0.0
            """,
            id="empty",
        ),
        pytest.param(
            """
            ## v1.0.0

            content 1

            ## v1.0.2

            content 2

            ## v1.0.3

            content 3
            """,
            """
            ## v1.0.0

            content 1

            content 2

            content 3
            """,
            id="simple",
        ),
        pytest.param(
            """
            ## v1.0.1

            content 1.1

            ### Sub 1

            sub 1.1

            ### Sub 2

            sub 1.2

            ## v1.0.2

            content 2.1

            ### Sub 0

            sub 2.0

            ### Sub 2

            sub 2.2

            ### Sub 1

            sub 2.1

            ### Sub 3

            sub 2.3

            """,
            """
            ## v1.0.1

            content 1.1

            content 2.1

            ### Sub 1

            sub 1.1

            sub 2.1

            ### Sub 2

            sub 1.2

            sub 2.2

            ### Sub 0

            sub 2.0

            ### Sub 3

            sub 2.3
            """,
            id="complex",
        ),
    ],
)
def test_merge_sections(input, expected):
    ctx = Context(
        pathlib.Path(),
        textwrap.dedent(input).strip(),
        Config(),
        False,
        None,  # type: ignore
    )

    changelog = parse(ctx)
    target = changelog.sections[0]
    for section in changelog.sections[1:]:
        merge_sections(target, section)

    ctx = Context(
        pathlib.Path(),
        textwrap.dedent(expected).strip(),
        Config(),
        False,
        None,  # type: ignore
    )

    result = parse(ctx)

    assert _render(target.to_tokens()) == _render(result.to_tokens())
    assert _remove_meta(target.to_tokens()) == _remove_meta(result.to_tokens())


@pytest.mark.parametrize(
    "a,b,result",
    [
        pytest.param(
            """
            """,
            """
            """,
            """
            """,
            id="empty",
        ),
        pytest.param(
            """
            content
            """,
            """
            """,
            """
            content
            """,
            id="left_empty",
        ),
        pytest.param(
            """
            """,
            """
            content
            """,
            """
            content
            """,
            id="right_empty",
        ),
        pytest.param(
            """
            content l
            """,
            """
            content r
            """,
            """
            content l

            content r
            """,
            id="two_paragraphs",
        ),
        pytest.param(
            """
            - content l
            """,
            """
            - content r
            """,
            """
            - content l
            - content r
            """,
            id="two_lists",
        ),
        pytest.param(
            """
            paragraph
            """,
            """
            - content r
            """,
            """
            paragraph
            - content r
            """,
            id="list_and_paragraph",
        ),
        pytest.param(
            """
            paragraph

            - content l
            """,
            """
            - content r

            paragraph
            """,
            """
            paragraph

            - content l
            - content r

            paragraph
            """,
            id="list_and_paragraph_merge",
        ),
    ],
)
def test_merge_subsections(a, b, result):
    parser = build_parser()
    left = SubSection(
        content=SyntaxTreeNode(
            _remove_meta(parser.parse(textwrap.dedent(a).strip()))
        ).children
    )
    right = SubSection(
        content=SyntaxTreeNode(
            _remove_meta(parser.parse(textwrap.dedent(b).strip()))
        ).children
    )
    result = SubSection(
        content=SyntaxTreeNode(
            _remove_meta(parser.parse(textwrap.dedent(result).strip()))
        ).children
    )

    merge_subsections(left, right)

    assert _render(left.to_tokens()) == _render(result.to_tokens())
    assert _remove_meta(left.to_tokens()) == _remove_meta(result.to_tokens())


def _remove_meta(tokens: list[Token]):
    for token in tokens:
        token.map = None
        for name in list(token.meta):
            if name.startswith("cl_"):
                del token.meta[name]
        if token.children:
            _remove_meta(token.children)
    return tokens


def _render(tokens: list[Token]):
    parser = build_parser()
    return parser.renderer.render(tokens, parser.options, {})
