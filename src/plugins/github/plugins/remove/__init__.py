from nonebot import logger, on_type
from nonebot.params import Depends
from nonebot.adapters.github import GitHubBot
from nonebot.adapters.github.event import (
    IssuesEdited,
    IssuesOpened,
    IssuesReopened,
    IssueCommentCreated,
)
from pydantic_core import PydanticCustomError


from src.plugins.github.models import IssueHandler
from src.plugins.github.depends import (
    bypass_git,
    get_installation_id,
    get_issue_number,
    get_repo_info,
    install_pre_commit_hooks,
    is_bot_triggered_workflow,
)
from src.plugins.github.depends import RepoInfo


from .render import render_comment, render_error
from .constants import BRANCH_NAME_PREFIX
from .depends import get_name_by_labels
from .utils import validate_author_info, process_pr_and_issue_title


async def check_rule(
    event: IssuesOpened | IssuesReopened | IssuesEdited | IssueCommentCreated,
    edit_type: list[str] = Depends(get_name_by_labels),
    is_bot: bool = Depends(is_bot_triggered_workflow),
) -> bool:
    if is_bot:
        return False
    if event.payload.issue.pull_request:
        logger.info("评论在拉取请求下，已跳过")
        return False
    if "remove" not in edit_type:
        logger.info("议题与删除无关，已跳过")
        return False
    return True


remove_check_matcher = on_type(
    (IssuesOpened, IssuesReopened, IssuesEdited, IssueCommentCreated),
    rule=check_rule,
)


@remove_check_matcher.handle(
    parameterless=[Depends(bypass_git), Depends(install_pre_commit_hooks)]
)
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

        handler = IssueHandler.model_construct(
            bot=bot, repo_info=repo_info, issue_number=issue_number, issue=issue
        )

        try:
            result = await validate_author_info(issue)
        except PydanticCustomError as err:
            logger.error(f"信息验证失败: {err}")
            await handler.comment_issue(await render_error(err))
            await remove_check_matcher.finish()

        title = f"{result.type}: Remove {result.name}"
        branch_name = f"{BRANCH_NAME_PREFIX}{issue_number}"

        # 处理拉取请求和议题标题
        await process_pr_and_issue_title(handler, result, branch_name, title)
        # 更新议题标题
        await handler.update_issue_title(title)

        await handler.comment_issue(await render_comment(result))
