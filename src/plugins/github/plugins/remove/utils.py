import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nonebot import logger
from pydantic_core import to_jsonable_python

from src.plugins.github.depends.utils import extract_issue_number_from_ref
from src.plugins.github.utils import run_shell_command
from src.plugins.github import plugin_config
from src.plugins.github.models import IssueHandler
from src.providers.validation.models import ValidationDict


from .constants import (
    COMMIT_MESSAGE_PREFIX,
    PUBLISH_PATH,
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


def dump_json(path: Path, data: Any):
    """保存 JSON 文件

    为减少文件大小，还需手动设置 separators
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_jsonable_python(data), f, ensure_ascii=False, indent=4)
        f.write("\n")


def update_file(remove_data: dict[str, Any]):
    """删除对应的包储存在 registry 里的数据"""
    logger.info("开始更新文件")

    for path in PUBLISH_PATH.values():
        data = load_json(path)

        # 删除对应的数据
        new_data = [item for item in data if item != remove_data]

        if data == new_data:
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
    run_shell_command(["git", "switch", "-C", branch_name])
    # 更新文件并提交更改
    update_file(result.data)
    handler.commit_and_push(commit_message, branch_name)
    # 创建拉取请求
    await handler.create_pull_request(
        plugin_config.input_config.base,
        title,
        branch_name,
        [REMOVE_LABEL],
    )


async def resolve_conflict_pull_requests(
    handler: IssueHandler,
    pulls: list["PullRequestSimple"] | list["PullRequest"],
):
    """根据关联的议题提交来解决冲突

    直接重新提交之前分支中的内容
    """
    logger.info("开始解决冲突")
    # 获取远程分支
    run_shell_command(["git", "fetch", "origin"])

    # 读取主分支的数据
    main_data = {}
    for type, path in PUBLISH_PATH.items():
        main_data[type] = load_json(path)

    run_shell_command(["git", "checkout", pull.head.ref])

    for pull in pulls:
        issue_number = extract_issue_number_from_ref(pull.head.ref)
        if not issue_number:
            logger.error(f"无法获取 {pull.title} 对应的议题编号")
            continue

        logger.info(f"正在处理 {pull.title}")
        if pull.draft:
            logger.info("拉取请求为草稿，跳过处理")
            continue
        
        # 切换到主分支
        run_shell_command(["git", "checkout", plugin_config.input_config.base])
        # 删除拉取的远程分支
        run_shell_command(["git", "branch", "-D", pull.head.ref])
        # 同步 main 分支到新的分支上
        run_shell_command(["git", "switch", "-C", pull.head.ref])
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
