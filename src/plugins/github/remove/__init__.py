from nonebot import logger, on_type
from nonebot.params import Depends
from nonebot.adapters.github import GitHubBot

from nonebot.adapters.github.event import (
    IssuesEdited,
    IssuesOpened,
    IssuesReopened,
    IssueCommentCreated,
)

from .constants import BRANCH_NAME_PREFIX, BOT_MARKER, NONEFLOW_MARKER
from .depends import (
    comment_issue,
    get_name_by_labels,
    process_pr_and_issue_title,
    validate_author_info,
)
from src.plugins.depends import get_installation_id, get_issue_number, get_repo_info
from src.plugins.depends import RepoInfo


async def check_rule(
    event: IssuesOpened | IssuesReopened | IssuesEdited | IssueCommentCreated,
    edit_type: list[str] = Depends(get_name_by_labels),
) -> bool:
    if (
        isinstance(event, IssueCommentCreated)
        and event.payload.comment.user
        and event.payload.comment.user.login.endswith(BOT_MARKER)
    ):
        logger.info("评论来自机器人，已跳过")
        return False
    if (
        isinstance(event, IssuesEdited)
        and event.payload.sender.login
        and event.payload.sender.login.endswith(BOT_MARKER)
    ):
        logger.info("议题的修改来自机器人，已跳过")
        return False
    if event.payload.issue.pull_request:
        logger.info("评论在拉取请求下，已跳过")
        return False
    if "remove" not in edit_type:
        logger.info("议题与删除无关，已跳过")
        await remove_check_matcher.finish()
    return True


remove_check_matcher = on_type(
    (IssuesOpened, IssuesReopened, IssuesEdited, IssueCommentCreated),
    rule=check_rule,
)


@remove_check_matcher.handle()
async def handle_remove_check(
    bot: GitHubBot,
    installation_id: int = Depends(get_installation_id),
    repo_info: RepoInfo = Depends(get_repo_info),
    issue_number: int = Depends(get_issue_number),
):
    async with bot.as_installation(installation_id):
        issue = (
            await bot.rest.issues.async_get(
                **repo_info.model_dump(), issue_number=issue_number
            )
        ).parsed_data

        if issue.state != "open":
            logger.info("议题未开启，已跳过")
            await remove_check_matcher.finish()

        result = await validate_author_info(issue)

        title = f"Remove {result.type}: {result.name}"
        branch_name = f"{BRANCH_NAME_PREFIX}{issue_number}"

        await process_pr_and_issue_title(
            bot, result, repo_info, branch_name, issue_number, title, issue
        )
        await comment_issue(
            bot,
            repo_info,
            issue_number,
            "OMG\n" + NONEFLOW_MARKER,
        )
