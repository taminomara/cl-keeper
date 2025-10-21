import logging

import pytest
import yuio.exec

from cl_keeper.config import ReleaseLinkPreset
from cl_keeper.vcs import detect_origin


@pytest.mark.parametrize(
    "origin,expected",
    [
        (None, None),
        ("https://example.com/", None),
        (
            "git+https://github.com/example/test.git",
            ReleaseLinkPreset.GITHUB.get_links().update_vars(
                dict(host="github.com", repo="example/test"), override=True
            ),
        ),
        (
            "git+https://gist.github.com/example/test.git",
            ReleaseLinkPreset.GITHUB.get_links().update_vars(
                dict(host="gist.github.com", repo="example/test"), override=True
            ),
        ),
        (
            "git+https://gitlab.com/example/test.git",
            ReleaseLinkPreset.GITLAB.get_links().update_vars(
                dict(host="gitlab.com", repo="example/test"), override=True
            ),
        ),
        pytest.param(
            "git+https://bitbucket.org/example/test.git",
            None,
            marks=pytest.mark.xfail(
                reason="https://github.com/nephila/giturlparse/pull/108"
            ),
        ),
        ("git+https://friendco.de/owner@user/repo.git", None),
    ],
)
def test_detect_origin(origin, expected, tmp_path):
    dir = tmp_path / "repo"
    dir.mkdir()
    yuio.exec.exec("git", "init", str(dir), cwd=dir)
    if origin:
        yuio.exec.exec(
            "git", "remote", "add", "remote", origin, level=logging.INFO, cwd=dir
        )
    result = detect_origin(dir)
    assert result == expected
