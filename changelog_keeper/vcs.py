import logging
import pathlib

import giturlparse
import yuio.git

from changelog_keeper.config import LinkTemplates, ReleaseLinkPreset
from changelog_keeper.context import Context, IssueScope, IssueSeverity
from changelog_keeper.parse import parse_version

logger = logging.getLogger(__name__)


def detect_origin(root: pathlib.Path) -> LinkTemplates | None:
    try:
        url = yuio.git.Repo(root).git("ls-remote", "--get-url").decode().strip()
    except (yuio.git.GitException, UnicodeDecodeError) as e:
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
            return ReleaseLinkPreset.GITHUB.get_links().update_vars(vars)
        case "gitlab":
            logger.info(
                "using link preset 'gitlab' with host %r, repo %r",
                vars["host"],
                vars["repo"],
            )
            return ReleaseLinkPreset.GITLAB.get_links().update_vars(vars)
        case _:
            logger.info(
                "failed to parse origin url from git: platform %r is not supported",
                parsed.platform,
            )
            return None


def get_repo_versions(root: pathlib.Path, ctx: Context) -> dict[str, yuio.git.Commit]:
    repo = yuio.git.Repo(root)
    repo_versions: dict[str, yuio.git.Commit] = {}
    for commit in repo.log("--tags", "--no-walk"):
        for tag in commit.tags:
            if tag.startswith(ctx.config.tag_prefix):
                version = tag[len(ctx.config.tag_prefix) :]
                if not parse_version(version, ctx):
                    ctx.issue(
                        "Tag %s doesn't doesn't follow %s specification.",
                        tag,
                        ctx.config.version_format.value,
                        scope=IssueScope.EXTERNAL,
                        severity=IssueSeverity.WEAK_WARNING,
                    )
                repo_versions[version] = commit
    return repo_versions
