import logging
import pathlib

import giturlparse
import yuio.git

from cl_keeper.config import (
    IssueCode,
    LinkTemplates,
    ReleaseLinkPreset,
    VersionFormat,
)
from cl_keeper.context import Context, IssueScope
from cl_keeper.model import RepoVersion
from cl_keeper.parse import canonize_version, parse_version

logger = logging.getLogger(__name__)


def detect_origin(root: pathlib.Path) -> LinkTemplates | None:
    try:
        url = yuio.git.Repo(root).git("ls-remote", "--get-url").decode().strip()
    except (yuio.git.GitError, UnicodeDecodeError) as e:
        logger.debug("failed to get origin url from git: %s", e)
        return None
    parsed = giturlparse.parse(url)
    if not parsed.valid:
        logger.debug("failed to parse origin url from git: %r", url)
        return None
    vars = {
        "repo": parsed.pathname.removesuffix(".git").strip("/"),
        "host": parsed.host,
    }
    logger.debug("detected origin url's platform as %r: %s", parsed.platform, url)
    match parsed.platform:
        case "github":
            logger.info(
                "using link preset 'github' with host %r, repo %r",
                vars["host"],
                vars["repo"],
            )
            return ReleaseLinkPreset.GITHUB.get_links().update_vars(vars, override=True)
        case "gitlab":
            logger.info(
                "using link preset 'gitlab' with host %r, repo %r",
                vars["host"],
                vars["repo"],
            )
            return ReleaseLinkPreset.GITLAB.get_links().update_vars(vars, override=True)
        case _:
            logger.info(
                "failed to parse origin url from git: platform %r is not supported",
                parsed.platform,
            )
            return None


def get_repo_versions(root: pathlib.Path, ctx: Context) -> dict[str, RepoVersion]:
    repo = yuio.git.Repo(root)
    repo_versions: dict[str, RepoVersion] = {}
    for commit in repo.log("--tags", "--no-walk"):
        for tag in commit.tags:
            if tag.startswith(ctx.config.tag_prefix):
                version = tag[len(ctx.config.tag_prefix) :]
                parsed_version = parse_version(version, ctx.config)
                if (
                    parsed_version is None
                    and ctx.config.version_format is not VersionFormat.NONE
                ):
                    ctx.issue(
                        IssueCode.INVALID_TAG,
                        "Tag `%s` doesn't follow %s specification",
                        tag,
                        ctx.config.version_format.value,
                        scope=IssueScope.EXTERNAL,
                    )
                canonized_version = (
                    canonize_version(parsed_version, ctx.config) or version
                )
                repo_versions[canonized_version] = RepoVersion(
                    version=version,
                    parsed_version=parsed_version,
                    canonized_version=canonized_version,
                    author_date=commit.author_datetime.date(),
                    committer_date=commit.committer_datetime.date(),
                )
    return repo_versions
