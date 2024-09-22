from ast import dump
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nonebot import logger
from githubkit.rest import Issue
from pydantic_core import PydanticCustomError

from plugins.github.depends.utils import extract_issue_number_from_ref
from plugins.github.utils import run_shell_command
from providers.store_test.utils import dump_json
from src.plugins.github import plugin_config
from src.plugins.github.models import IssueHandler
from src.providers.validation import extract_publish_info_from_issue
from src.providers.validation.models import PublishType, ValidationDict

from .constants import (
    COMMIT_MESSAGE_PREFIX,
    PUBLISH_PATH,
    REMOVE_HOMEPAGE_PATTERN,
    REMOVE_LABEL,
)

if TYPE_CHECKING:
    from githubkit.rest import (
        Issue,
        PullRequest,
        PullRequestSimple,
    )


def load_json(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def validate_author_info(issue: Issue) -> ValidationDict:
    """
    根据主页链接与作者信息删除对应的包储存在商店里的数据
    """

    homepage = extract_publish_info_from_issue(
        {
            "homepage": REMOVE_HOMEPAGE_PATTERN,
        },
        issue.body or "",
    ).get("homepage")
    author = issue.user.login if issue.user else ""
    author_id = issue.user.id if issue.user else None

    store_data = {
        PublishType.PLUGIN: plugin_config.input_config.plugin_path,
        PublishType.ADAPTER: plugin_config.input_config.adapter_path,
        PublishType.BOT: plugin_config.input_config.bot_path,
    }

    for type, path in store_data.items():
        if not path.exists():
            logger.info(f"{type} 数据文件不存在，跳过")
            continue

        data: list[dict[str, str]] = load_json(path)
        for item in data:
            if item.get("homepage") == homepage:
                logger.info(f"找到匹配的 {type} 数据 {item}")

                # author_id 暂时没有储存到数据里, 所以暂时不校验
                if item.get("author") == author or (
                    item.get("author_id") is not None
                    and item.get("author_id") == author_id
                ):
                    return ValidationDict(
                        valid=True,
                        data=item,
                        type=type,
                        name=item.get("name") or item.get("module_name") or "",
                        author=author,
                        errors=[],
                    )
                raise PydanticCustomError("author_info", "作者信息不匹配")
    raise PydanticCustomError("not_found", "没有包含对应主页链接的包")


def update_file(remove_data: dict[str, Any]):
    """删除对应的包储存在 registry 里的数据"""
    logger.info("开始更新文件")

    for path in PUBLISH_PATH.values():
        data = load_json(path)

        # 删除对应的数据
        new_data = [item for item in data if item != remove_data]

        if data == new_data:
            logger.info(f"没有找到对应的数据 {remove_data}")
            continue

        # 如果数据发生变化则更新文件
        dump_json(path, new_data)
        logger.info(f"已更新 {path.name} 文件")


async def process_pr_and_issue_title(
    handler: IssueHandler,
    result: ValidationDict,
    branch_name: str,
    title: str,
):
    """
    根据发布信息合法性创建拉取请求或将请求改为草稿，并修改议题标题
    """
    commit_message = f"{COMMIT_MESSAGE_PREFIX} {result.name} (#{handler.issue_number})"

    # 切换分支
    handler.switch_branch(branch_name)
    # 更新文件并提交更改
    update_file(result.data)
    handler.commit_and_push(commit_message, branch_name)
    # 创建拉取请求
    await handler.create_pull_request(
        plugin_config.input_config.base,
        title,
        branch_name,
        REMOVE_LABEL,
    )


async def resolve_conflict_pull_requests(
    handler: IssueHandler,
    pulls: list["PullRequestSimple"] | list["PullRequest"],
):
    """根据关联的议题提交来解决冲突

    直接重新提交之前分支中的内容
    """
    # 获取远程分支
    run_shell_command(["git", "fetch", "origin"])
    # 切换到主分支
    handler.switch_branch(plugin_config.input_config.base)

    # 读取主分支的数据
    main_data = {}
    for type, path in PUBLISH_PATH.items():
        main_data[type] = load_json(path)

    for pull in pulls:
        issue_number = extract_issue_number_from_ref(pull.head.ref)
        if not issue_number:
            logger.error(f"无法获取 {pull.title} 对应的议题编号")
            continue

        logger.info(f"正在处理 {pull.title}")
        if pull.draft:
            logger.info("拉取请求为草稿，跳过处理")
            continue

        # 切换到该拉取请求对应的分支
        handler.switch_branch(pull.head.ref)

        # 读取拉取请求分支的数据
        pull_data = {}
        for type, path in PUBLISH_PATH.items():
            pull_data[type] = load_json(path)

        for type, data in pull_data.items():
            if data != main_data[type]:
                logger.info(f"{type} 数据发生变化，开始解决冲突")

                # 该分支存在的数据，但主分支已经删除的元素
                remove_items = [item for item in data if item not in main_data[type]]

                logger.info(f"找到冲突的 {type} 数据 {remove_items}")
                for item in remove_items:
                    update_file(item)
                handler.commit_and_push(
                    f"{COMMIT_MESSAGE_PREFIX} {pull.title} (#{issue_number})",
                    pull.head.ref,
                )
                logger.info(f"已解决 {type} 数据冲突")
        logger.info(f"{pull.title} 处理完毕")
