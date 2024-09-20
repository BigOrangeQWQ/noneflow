import json
from pathlib import Path
import subprocess
from githubkit.exception import RequestFailed

from githubkit.rest import (
    PullRequestPropLabelsItems,
    PullRequestSimple,
    WebhookIssueCommentCreatedPropIssueAllof0PropLabelsItems,
    WebhookIssuesEditedPropIssuePropLabelsItems,
    WebhookIssuesOpenedPropIssuePropLabelsItems,
    WebhookIssuesReopenedPropIssueMergedLabels,
    WebhookPullRequestReviewSubmittedPropPullRequestPropLabelsItems,
)
from githubkit.typing import Missing
from nonebot import logger
from nonebot.adapters.github import (
    Bot,
    GitHubBot,
    IssueCommentCreated,
    IssuesEdited,
    IssuesOpened,
    IssuesReopened,
    PullRequestClosed,
    PullRequestReviewSubmitted,
)
from githubkit.rest import Issue
from nonebot.params import Depends

from plugins.depends.utils import run_shell_command

from .constants import (
    COMMIT_MESSAGE_PREFIX,
    NONEFLOW_MARKER,
    REMOVE_PLUGIN_MODULE_NAME_PATTERN,
    REMOVE_PROJECT_LINK_PATTERN,
)
from src.plugins.depends.models import RepoInfo
from src.providers.validation import extract_publish_info_from_issue
from src.providers.validation.models import PublishType, ValidationDict
from .. import plugin_config


async def create_pull_request(
    bot: Bot,
    repo_info: RepoInfo,
    result: ValidationDict,
    branch_name: str,
    issue_number: int,
    title: str,
):
    """创建拉取请求

    同时添加对应标签
    内容关联上对应的议题
    """
    # 关联相关议题，当拉取请求合并时会自动关闭对应议题
    body = f"resolve #{issue_number}"

    try:
        # 创建拉取请求
        resp = await bot.rest.pulls.async_create(
            **repo_info.model_dump(),
            title=title,
            body=body,
            base=plugin_config.input_config.base,
            head=branch_name,
        )
        pull = resp.parsed_data

        # 自动给拉取请求添加标签
        await bot.rest.issues.async_add_labels(
            **repo_info.model_dump(),
            issue_number=pull.number,
            labels=[result.type.value],
        )
        logger.info("拉取请求创建完毕")
    except RequestFailed:
        logger.info("该分支的拉取请求已创建，请前往查看")

        pull = (
            await bot.rest.pulls.async_list(
                **repo_info.model_dump(), head=f"{repo_info.owner}:{branch_name}"
            )
        ).parsed_data[0]
        if pull.title != title:
            await bot.rest.pulls.async_update(
                **repo_info.model_dump(), pull_number=pull.number, title=title
            )
            logger.info(f"拉取请求标题已修改为 {title}")
        if pull.draft:
            await bot.async_graphql(
                query="""mutation markPullRequestReadyForReview($pullRequestId: ID!) {
                    markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) {
                        clientMutationId
                    }
                }""",
                variables={"pullRequestId": pull.node_id},
            )
            logger.info("拉取请求已标记为可评审")


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


def get_name_by_labels(
    labels: list[PullRequestPropLabelsItems]
    | list[WebhookPullRequestReviewSubmittedPropPullRequestPropLabelsItems]
    | Missing[list[WebhookIssuesOpenedPropIssuePropLabelsItems]]
    | Missing[list[WebhookIssuesReopenedPropIssueMergedLabels]]
    | Missing[list[WebhookIssuesEditedPropIssuePropLabelsItems]]
    | list[WebhookIssueCommentCreatedPropIssueAllof0PropLabelsItems] = Depends(
        get_labels
    ),
) -> list[str]:
    """通过标签获取名称"""
    label_names = []
    if not labels:
        return label_names

    for label in labels:
        if label.name:
            label_names.append(label.name)
    return label_names


async def comment_issue(bot: Bot, repo_info: RepoInfo, issue_number: int, comment: str):
    """在议题中发布评论"""
    logger.info("开始发布评论")

    # 重复利用评论
    # 如果发现之前评论过，直接修改之前的评论
    comments = (
        await bot.rest.issues.async_list_comments(
            **repo_info.model_dump(), issue_number=issue_number
        )
    ).parsed_data
    reusable_comment = next(
        filter(lambda x: NONEFLOW_MARKER in (x.body if x.body else ""), comments),
        None,
    )

    if reusable_comment:
        logger.info(f"发现已有评论 {reusable_comment.id}，正在修改")
        if reusable_comment.body != comment:
            await bot.rest.issues.async_update_comment(
                **repo_info.model_dump(), comment_id=reusable_comment.id, body=comment
            )
            logger.info("评论修改完成")
        else:
            logger.info("评论内容无变化，跳过修改")
    else:
        await bot.rest.issues.async_create_comment(
            **repo_info.model_dump(), issue_number=issue_number, body=comment
        )
        logger.info("评论创建完成")


def load_json(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="UTF-8") as f:
        return json.load(f)


async def validate_author_info(issue: Issue) -> ValidationDict:
    """
    根据主页链接与作者信息删除对应的包储存在商店里的数据，若存在则返回 True
    """

    issue_data = extract_publish_info_from_issue(
        {
            "project_link": REMOVE_PLUGIN_MODULE_NAME_PATTERN,
            "module_name": REMOVE_PROJECT_LINK_PATTERN,
        },
        issue.body or "",
    )
    project_link = issue_data.get("project_link")
    module_name = issue_data.get("module_name")
    author = issue.user.login if issue.user else ""
    author_id = issue.user.id if issue.user else None

    store_data = {
        PublishType.PLUGIN: plugin_config.input_config.plugin_path,
        PublishType.ADAPTER: plugin_config.input_config.adapter_path,
        PublishType.BOT: plugin_config.input_config.bot_path,
    }
    logger.info(f"self info {project_link}, {module_name}, {author}, {author_id}")
    for type, path in store_data.items():
        if not path.exists():
            continue

        data = load_json(path)
        for item in data:
            if (
                item.get("module_name") == module_name
                and item.get("project_link") == project_link
                and item.get("author") == author
            ):
                logger.info(f"找到匹配的 {type} 数据")
                if (
                    item.get("author_id") is not None
                    and item.get("author_id") != author_id
                ):
                    continue

                return ValidationDict(
                    valid=True,
                    data=item,
                    type=type,
                    name=item.get("name") or "",
                    author=author,
                    errors=[],
                )

    return ValidationDict(
        valid=False,
        type=PublishType.PLUGIN,
        name=project_link or module_name or "not found",
        author=author,
    )


def update_file(result: ValidationDict):
    with open(plugin_config.input_config.plugin_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        data.remove(result.data)
    with open(plugin_config.input_config.plugin_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# 验证成不成功，作者的信息，


def commit_and_push(message: str, branch_name: str, author: str):
    run_shell_command(["git", "config", "--global", "user.name", author])
    user_email = f"{author}@users.noreply.github.com"
    run_shell_command(["git", "config", "--global", "user.email", user_email])
    run_shell_command(["git", "add", "-A"])
    try:
        run_shell_command(["git", "commit", "-m", message])
    except Exception:
        # 如果提交失败，因为是 pre-commit hooks 格式化代码导致的，所以需要再次提交
        run_shell_command(["git", "add", "-A"])
        run_shell_command(["git", "commit", "-m", message])

    try:
        run_shell_command(["git", "fetch", "origin"])
        r = run_shell_command(["git", "diff", f"origin/{branch_name}", branch_name])
        if r.stdout:
            raise Exception
        else:
            logger.info("检测到本地分支与远程分支一致，跳过推送")
    except Exception:
        logger.info("检测到本地分支与远程分支不一致，尝试强制推送")
        run_shell_command(["git", "push", "origin", branch_name, "-f"])


async def process_pr_and_issue_title(
    bot: Bot,
    result: ValidationDict,
    repo_info: RepoInfo,
    branch_name: str,
    issue_number: int,
    title: str,
    issue: "Issue",
):
    """
    根据发布信息合法性创建拉取请求或将请求改为草稿，并修改议题标题
    """

    if result.valid:
        run_shell_command(["git", "switch", "-C", branch_name])
        # 更新文件并提交更改
        commit_message = f"{COMMIT_MESSAGE_PREFIX} {result.valid} (#{issue_number})"
        commit_and_push(commit_message, branch_name, "")
        # 创建拉取请求
        await create_pull_request(
            bot, repo_info, result, branch_name, issue_number, title
        )
    else:
        # 如果之前已经创建了拉取请求，则将其转换为草稿
        pulls = (
            await bot.rest.pulls.async_list(
                **repo_info.model_dump(), head=f"{repo_info.owner}:{branch_name}"
            )
        ).parsed_data
        if pulls and (pull := pulls[0]) and not pull.draft:
            await bot.async_graphql(
                query="""mutation convertPullRequestToDraft($pullRequestId: ID!) {
                    convertPullRequestToDraft(input: {pullRequestId: $pullRequestId}) {
                        clientMutationId
                    }
                }""",
                variables={"pullRequestId": pull.node_id},
            )
            logger.info("删除没通过检查，已将之前的拉取请求转换为草稿")
        else:
            logger.info("没通过检查，暂不创建拉取请求")

    # 修改议题标题
    # 需要等创建完拉取请求并打上标签后执行
    # 不然会因为修改议题触发 Actions 导致标签没有正常打上
    if issue.title != title:
        await bot.rest.issues.async_update(
            **repo_info.model_dump(), issue_number=issue_number, title=title
        )
        logger.info(f"议题标题已修改为 {title}")
