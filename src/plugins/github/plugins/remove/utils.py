import json
from pathlib import Path
from typing import Any

from nonebot import logger
from githubkit.rest import Issue
from pydantic_core import PydanticCustomError

from src.plugins.github import plugin_config
from src.plugins.github.models import IssueHandler
from src.providers.validation import extract_publish_info_from_issue
from src.providers.validation.models import PublishType, ValidationDict

from .constants import COMMIT_MESSAGE_PREFIX, REMOVE_HOMEPAGE_PATTERN


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
                raise PydanticCustomError("no_equal", "作者信息不匹配")
    raise PydanticCustomError("not_found", "没有包含对应主页链接的包")


def update_file(remove_data: dict[str, Any]):
    """删除对应的包储存在 registry 里的数据"""
    logger.info("开始更新文件")
    data: list[dict[str, str]] = []
    with open(plugin_config.input_config.plugin_path, encoding="utf-8") as f:
        data = json.load(f)
        for item in data:
            if item == remove_data:
                data.remove(item)
                break

    with open(plugin_config.input_config.plugin_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


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
        result.type.value,
    )
