from nonebot.adapters.github import (
    GitHubBot,
    IssueCommentCreated,
    IssuesEdited,
    IssuesOpened,
    IssuesReopened,
    PullRequestClosed,
    PullRequestReviewSubmitted,
)
from nonebot.params import Depends

from .utils import extract_issue_number_from_ref, run_shell_command
from .models import RepoInfo


def bypass_git():
    """绕过检查"""
    # https://github.blog/2022-04-18-highlights-from-git-2-36/#stricter-repository-ownership-checks
    run_shell_command(["git", "config", "--global", "safe.directory", "*"])


def install_pre_commit_hooks():
    """安装 pre-commit 钩子"""
    run_shell_command(["pre-commit", "install", "--install-hooks"])


def get_labels(
    event: PullRequestClosed
    | PullRequestReviewSubmitted
    | IssuesOpened
    | IssuesReopened
    | IssuesEdited
    | IssueCommentCreated,
):
    """获取议题或拉取请求的标签"""
    if isinstance(event, PullRequestClosed | PullRequestReviewSubmitted):
        labels = event.payload.pull_request.labels
    else:
        labels = event.payload.issue.labels
    return labels


def get_issue_title(
    event: IssuesOpened | IssuesReopened | IssuesEdited | IssueCommentCreated,
):
    """获取议题标题"""
    return event.payload.issue.title


def get_repo_info(
    event: PullRequestClosed
    | PullRequestReviewSubmitted
    | IssuesOpened
    | IssuesReopened
    | IssuesEdited
    | IssueCommentCreated,
) -> RepoInfo:
    """获取仓库信息"""
    repo = event.payload.repository
    return RepoInfo(owner=repo.owner.login, repo=repo.name)


async def get_installation_id(
    bot: GitHubBot,
    repo_info: RepoInfo = Depends(get_repo_info),
) -> int:
    """获取 GitHub App 的 Installation ID"""
    installation = (
        await bot.rest.apps.async_get_repo_installation(**repo_info.model_dump())
    ).parsed_data
    return installation.id


def get_issue_number(
    event: IssuesOpened | IssuesReopened | IssuesEdited | IssueCommentCreated,
) -> int:
    """获取议题编号"""
    return event.payload.issue.number


def get_related_issue_number(event: PullRequestClosed) -> int | None:
    """获取 PR 相关联的议题号"""
    ref = event.payload.pull_request.head.ref
    related_issue_number = extract_issue_number_from_ref(ref)
    return related_issue_number
