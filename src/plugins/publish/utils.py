import asyncio
import json
import re
import subprocess
from typing import TYPE_CHECKING, Any
from githubkit.exception import RequestFailed
from githubkit.typing import Missing
from nonebot import logger
from nonebot.adapters.github import Bot, GitHubBot

from src.utils.validation import (
    PublishType,
    ValidationDict,
    extract_publish_info_from_issue,
    validate_info,
)
from src.utils.constants import DOCKER_IMAGES
from src.utils.docker_test import DockerPluginTest
from src.utils.plugin_test import strip_ansi
from utils.store_test.models import DockerTestResult, Metadata

from .config import plugin_config
from .constants import (
    ADAPTER_DESC_PATTERN,
    ADAPTER_HOMEPAGE_PATTERN,
    ADAPTER_MODULE_NAME_PATTERN,
    ADAPTER_NAME_PATTERN,
    BOT_DESC_PATTERN,
    BOT_HOMEPAGE_PATTERN,
    BOT_NAME_PATTERN,
    BRANCH_NAME_PREFIX,
    COMMIT_MESSAGE_PREFIX,
    ISSUE_FIELD_PATTERN,
    ISSUE_FIELD_TEMPLATE,
    NONEFLOW_MARKER,
    PLUGIN_CONFIG_PATTERN,
    PLUGIN_DESC_PATTERN,
    PLUGIN_HOMEPAGE_PATTERN,
    PLUGIN_MODULE_NAME_PATTERN,
    PLUGIN_NAME_PATTERN,
    PLUGIN_STRING_LIST,
    PLUGIN_SUPPORTED_ADAPTERS_PATTERN,
    PLUGIN_TYPE_PATTERN,
    PROJECT_LINK_PATTERN,
    SKIP_PLUGIN_TEST_COMMENT,
    TAGS_PATTERN,
)
from .models import RepoInfo
from .render import render_comment

if TYPE_CHECKING:
    from githubkit.rest import (
        Issue,
        PullRequest,
        PullRequestPropLabelsItems,
        PullRequestSimple,
        PullRequestSimplePropLabelsItems,
        WebhookIssueCommentCreatedPropIssueAllof0PropLabelsItems,
        WebhookIssuesEditedPropIssuePropLabelsItems,
        WebhookIssuesOpenedPropIssuePropLabelsItems,
        WebhookIssuesReopenedPropIssueMergedLabels,
        WebhookPullRequestReviewSubmittedPropPullRequestPropLabelsItems,
    )


def run_shell_command(command: list[str]):
    """运行 shell 命令

    如果遇到错误则抛出异常
    """
    logger.info(f"运行命令: {command}")
    try:
        r = subprocess.run(command, check=True, capture_output=True)
        logger.debug(f"命令输出: \n{r.stdout.decode()}")
    except subprocess.CalledProcessError as e:
        logger.debug("命令运行失败")
        logger.debug(f"命令输出: \n{e.stdout.decode()}")
        logger.debug(f"命令错误: \n{e.stderr.decode()}")
        raise
    return r


def get_type_by_labels(
    labels: list["PullRequestPropLabelsItems"]
    | list["PullRequestSimplePropLabelsItems"]
    | list["WebhookPullRequestReviewSubmittedPropPullRequestPropLabelsItems"]
    | Missing[list["WebhookIssuesOpenedPropIssuePropLabelsItems"]]
    | Missing[list["WebhookIssuesReopenedPropIssueMergedLabels"]]
    | Missing[list["WebhookIssuesEditedPropIssuePropLabelsItems"]]
    | list["WebhookIssueCommentCreatedPropIssueAllof0PropLabelsItems"],
) -> PublishType | None:
    """通过标签获取类型"""
    if not labels:
        return None

    for label in labels:
        if isinstance(label, str):
            continue
        if label.name == PublishType.BOT.value:
            return PublishType.BOT
        if label.name == PublishType.PLUGIN.value:
            return PublishType.PLUGIN
        if label.name == PublishType.ADAPTER.value:
            return PublishType.ADAPTER


def get_type_by_title(title: str) -> PublishType | None:
    """通过标题获取类型"""
    if title.startswith(f"{PublishType.BOT.value}:"):
        return PublishType.BOT
    if title.startswith(f"{PublishType.PLUGIN.value}:"):
        return PublishType.PLUGIN
    if title.startswith(f"{PublishType.ADAPTER.value}:"):
        return PublishType.ADAPTER


def get_type_by_commit_message(message: str) -> PublishType | None:
    """通过提交信息获取类型"""
    if message.startswith(f"{COMMIT_MESSAGE_PREFIX} {PublishType.BOT.value.lower()}"):
        return PublishType.BOT
    if message.startswith(
        f"{COMMIT_MESSAGE_PREFIX} {PublishType.PLUGIN.value.lower()}"
    ):
        return PublishType.PLUGIN
    if message.startswith(
        f"{COMMIT_MESSAGE_PREFIX} {PublishType.ADAPTER.value.lower()}"
    ):
        return PublishType.ADAPTER


def commit_and_push(result: ValidationDict, branch_name: str, issue_number: int):
    """提交并推送"""
    commit_message = f"{COMMIT_MESSAGE_PREFIX} {result.type.value.lower()} {result.name} (#{issue_number})"

    run_shell_command(["git", "config", "--global", "user.name", result.author])
    user_email = f"{result.author}@users.noreply.github.com"
    run_shell_command(["git", "config", "--global", "user.email", user_email])
    run_shell_command(["git", "add", "-A"])
    try:
        run_shell_command(["git", "commit", "-m", commit_message])
    except Exception:
        # 如果提交失败，因为是 pre-commit hooks 格式化代码导致的，所以需要再次提交
        run_shell_command(["git", "add", "-A"])
        run_shell_command(["git", "commit", "-m", commit_message])

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


def extract_issue_number_from_ref(ref: str) -> int | None:
    """从 Ref 中提取议题号"""
    match = re.search(rf"{BRANCH_NAME_PREFIX}(\d+)", ref)
    if match:
        return int(match.group(1))


def extract_name_from_title(title: str, publish_type: PublishType) -> str | None:
    """从标题中提取名称"""
    match = re.search(rf"{publish_type.value}: (.+)", title)
    if match:
        return match.group(1)


async def validate_plugin_info_from_issue(issue: "Issue") -> ValidationDict:
    """从议题中提取插件信息"""
    body: str = issue.body if issue.body else ""
    author: str | None = issue.user.login if issue.user else ""
    raw_data: dict[str, Any] = extract_publish_info_from_issue(
        {
            "module_name": PLUGIN_MODULE_NAME_PATTERN,
            "project_link": PROJECT_LINK_PATTERN,
            "test_config": PLUGIN_CONFIG_PATTERN,
            "tags": TAGS_PATTERN,
        },
        body,
    )
    test_config: str = raw_data["test_config"]
    module_name: str = raw_data["module_name"]
    project_link: str = raw_data["project_link"]

    with plugin_config.input_config.plugin_path.open("r", encoding="utf-8") as f:
        previous_data: list[dict[str, str]] = json.load(f)

    plugin_test_result: DockerTestResult = await DockerPluginTest(
        DOCKER_IMAGES, project_link, module_name, test_config
    ).run("3.10")
    plugin_test_metadata: Metadata | None = plugin_test_result.metadata
    plugin_test_output: str = strip_ansi("".join(plugin_test_result.outputs))

    logger.info(f"插件测试结果: {plugin_test_result}")
    logger.info(f"插件元数据: {plugin_test_metadata}")
    raw_data.update(
        {
            "plugin_test_load": plugin_test_result.load,
            "result": plugin_test_result,
            "output": plugin_test_output,
            "metadata": plugin_test_metadata,
            "previous_data": previous_data,
            "author": author,
        }
    )
    # 如果插件测试被跳过，则从议题中获取信息
    if plugin_config.skip_plugin_test:
        plugin_info = extract_publish_info_from_issue(
            {
                "name": PLUGIN_NAME_PATTERN,
                "desc": PLUGIN_DESC_PATTERN,
                "homepage": PLUGIN_HOMEPAGE_PATTERN,
                "type": PLUGIN_TYPE_PATTERN,
                "supported_adapters": PLUGIN_SUPPORTED_ADAPTERS_PATTERN,
            },
            body,
        )
        raw_data.update(plugin_info)
    elif plugin_test_metadata:
        raw_data.update(plugin_test_metadata)
        raw_data["desc"] = raw_data.get("description")
    else:
        # 插件缺少元数据
        # 可能为插件测试未通过，或者插件未按规范编写
        raw_data["name"] = project_link

    # 如果升级至 pydantic 2 后，可以使用 validation-context
    validation_context = {
        "previous_data": raw_data.get("previous_data"),
        "skip_plugin_test": raw_data.get("skip_plugin_test"),
        "plugin_test_output": raw_data.get("plugin_test_output"),
    }

    validate_data = validate_info(PublishType.PLUGIN, raw_data, validation_context)

    # 如果是插件，还需要额外验证插件加载测试结果
    if (
        validate_data.data.get("plugin_test_metadata") is None
        and not plugin_config.skip_plugin_test
    ):
        # 如果没有跳过测试且缺少插件元数据，则跳过元数据相关的错误
        # 因为这个时候这些项都会报错，错误在此时没有意义
        metadata_keys = ["name", "desc", "homepage", "type", "supported_adapters"]
        validate_data.errors = [
            error
            for error in validate_data.errors
            if error["loc"][0] not in metadata_keys
        ]
        # 元数据缺失时，需要删除元数据相关的字段
        for key in metadata_keys:
            validate_data.data.pop(key, None)

    return validate_data


async def validate_bot_info_from_issue(issue: "Issue") -> ValidationDict:
    body = issue.body if issue.body else ""
    author = issue.user.login if issue.user else ""

    raw_data: dict[str, str] = extract_publish_info_from_issue(
        {
            "name": BOT_NAME_PATTERN,
            "desc": BOT_DESC_PATTERN,
            "homepage": BOT_HOMEPAGE_PATTERN,
            "tags": TAGS_PATTERN,
        },
        body,
    )
    raw_data["author"] = author

    return validate_info(PublishType.BOT, raw_data)


async def validate_adapter_info_from_issue(issue: "Issue") -> ValidationDict:
    body = issue.body if issue.body else ""
    author = issue.user.login if issue.user else ""
    raw_data: dict[str, Any] = extract_publish_info_from_issue(
        {
            "module_name": ADAPTER_MODULE_NAME_PATTERN,
            "project_link": PROJECT_LINK_PATTERN,
            "name": ADAPTER_NAME_PATTERN,
            "desc": ADAPTER_DESC_PATTERN,
            "homepage": ADAPTER_HOMEPAGE_PATTERN,
            "tags": TAGS_PATTERN,
        },
        body,
    )
    with plugin_config.input_config.adapter_path.open("r", encoding="utf-8") as f:
        previous_data: list[dict[str, str]] = json.load(f)
    raw_data["author"] = author
    raw_data["previous_data"] = previous_data

    return validate_info(PublishType.ADAPTER, raw_data)


async def resolve_conflict_pull_requests(
    pulls: list["PullRequestSimple"] | list["PullRequest"],
):
    """根据关联的议题提交来解决冲突

    直接重新提交之前分支中的内容
    """
    for pull in pulls:
        issue_number = extract_issue_number_from_ref(pull.head.ref)
        if not issue_number:
            logger.error(f"无法获取 {pull.title} 对应的议题编号")
            continue

        logger.info(f"正在处理 {pull.title}")
        if pull.draft:
            logger.info("拉取请求为草稿，跳过处理")
            continue

        publish_type = get_type_by_labels(pull.labels)
        if publish_type:
            # 需要先获取远程分支，否则无法切换到对应分支
            run_shell_command(["git", "fetch", "origin"])
            # 因为当前分支为触发处理冲突的分支，所以需要切换到每个拉取请求对应的分支
            run_shell_command(["git", "checkout", pull.head.ref])
            # 获取数据
            result = generate_validation_dict_from_file(
                publish_type,
                # 提交时的 commit message 中包含插件名称
                # 但因为仓库内的 plugins.json 中没有插件名称，所以需要从标题中提取
                extract_name_from_title(pull.title, publish_type)
                if publish_type == PublishType.PLUGIN
                else None,
            )
            # 回到主分支
            run_shell_command(["git", "checkout", plugin_config.input_config.base])
            # 切换到对应分支
            run_shell_command(["git", "switch", "-C", pull.head.ref])
            update_file(result)
            commit_and_push(result, pull.head.ref, issue_number)
            logger.info("拉取请求更新完毕")


def generate_validation_dict_from_file(
    publish_type: PublishType,
    name: str | None = None,
) -> ValidationDict:
    """从文件中获取发布所需数据"""
    match publish_type:
        case PublishType.ADAPTER:
            with plugin_config.input_config.adapter_path.open(
                "r", encoding="utf-8"
            ) as f:
                data: list[dict[str, str]] = json.load(f)
            raw_data = data[-1]
        case PublishType.BOT:
            with plugin_config.input_config.bot_path.open("r", encoding="utf-8") as f:
                data: list[dict[str, str]] = json.load(f)
            raw_data = data[-1]
        case PublishType.PLUGIN:
            with plugin_config.input_config.plugin_path.open(
                "r", encoding="utf-8"
            ) as f:
                data: list[dict[str, str]] = json.load(f)
            raw_data = data[-1]
            assert name, "插件名称不能为空"
            raw_data["name"] = name

    return ValidationDict(
        valid=True,
        type=publish_type,
        name=raw_data["name"],
        author=raw_data["author"],
        data=raw_data,
        errors=[],
    )


def update_file(result: ValidationDict) -> None:
    """更新文件"""
    new_data = result.data
    match result.type:
        case PublishType.ADAPTER:
            path = plugin_config.input_config.adapter_path
        case PublishType.BOT:
            path = plugin_config.input_config.bot_path
        case PublishType.PLUGIN:
            path = plugin_config.input_config.plugin_path
            # nonebot2 仓库内只需要这部分数据
            new_data = {
                "module_name": new_data["module_name"],
                "project_link": new_data["project_link"],
                "author": new_data["author"],
                "tags": new_data["tags"],
                "is_official": new_data["is_official"],
            }

    logger.info(f"正在更新文件: {path}")
    with path.open("r", encoding="utf-8") as f:
        data: list[dict[str, str]] = json.load(f)
    with path.open("w", encoding="utf-8") as f:
        data.append(new_data)
        json.dump(data, f, ensure_ascii=False, indent=2)
        # 结尾加上换行符，不然会被 pre-commit fix
        f.write("\n")
    logger.info("文件更新完成")


async def should_skip_plugin_test(
    bot: Bot,
    repo_info: RepoInfo,
    issue_number: int,
) -> bool:
    """判断是否跳过插件测试"""
    comments = (
        await bot.rest.issues.async_list_comments(
            **repo_info.model_dump(), issue_number=issue_number
        )
    ).parsed_data
    for comment in comments:
        author_association = comment.author_association
        if comment.body == SKIP_PLUGIN_TEST_COMMENT and author_association in [
            "OWNER",
            "MEMBER",
        ]:
            return True
    return False


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


async def comment_issue(
    bot: Bot, repo_info: RepoInfo, issue_number: int, result: ValidationDict
):
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

    comment = await render_comment(result, bool(reusable_comment))
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


async def ensure_issue_content(
    bot: Bot, repo_info: RepoInfo, issue_number: int, issue_body: str
):
    """确保议题内容中包含所需的插件信息"""
    new_content = []

    for name in PLUGIN_STRING_LIST:
        pattern = re.compile(ISSUE_FIELD_PATTERN.format(name))
        if not pattern.search(issue_body):
            new_content.append(ISSUE_FIELD_TEMPLATE.format(name))

    if new_content:
        new_content.append(issue_body)
        await bot.rest.issues.async_update(
            **repo_info.model_dump(),
            issue_number=issue_number,
            body="\n\n".join(new_content),
        )
        logger.info("检测到议题内容缺失，已更新")


async def trigger_registry_update(
    bot: GitHubBot, repo_info: RepoInfo, publish_type: PublishType, issue: "Issue"
):
    """通过 repository_dispatch 触发商店列表更新"""
    if publish_type == PublishType.PLUGIN:
        config = PLUGIN_CONFIG_PATTERN.search(issue.body) if issue.body else ""
        # 插件测试是否被跳过
        plugin_config.skip_plugin_test = await should_skip_plugin_test(
            bot, repo_info, issue.number
        )
        if plugin_config.skip_plugin_test:
            # 重新从议题中获取数据，并验证，防止中间有人修改了插件信息
            # 因为此时已经将新插件的信息添加到插件列表中
            # 直接将插件列表变成空列表，避免重新验证时出现重复报错
            with plugin_config.input_config.plugin_path.open(
                "w", encoding="utf-8"
            ) as f:
                json.dump([], f)
            result = await validate_plugin_info_from_issue(issue)
            logger.debug(f"插件信息验证结果: {result}")
            if not result.valid:
                logger.error("插件信息验证失败，跳过触发商店列表更新")
                return

            client_payload = {
                "type": publish_type.value,
                "key": f"{result.data['project_link']}:{result.data['module_name']}",
                "config": config.group(1) if config else "",
                "data": json.dumps(result.data),
            }
        else:
            # 从议题中获取的插件信息
            # 这样如果在 json 更新后再次运行也不会获取到不属于该插件的信息
            body = issue.body if issue.body else ""
            module_name = PLUGIN_MODULE_NAME_PATTERN.search(body)
            project_link = PROJECT_LINK_PATTERN.search(body)
            config = PLUGIN_CONFIG_PATTERN.search(body)

            if not module_name or not project_link:
                logger.error("无法从议题中获取插件信息，跳过触发商店列表更新")
                return

            module_name = module_name.group(1)
            project_link = project_link.group(1)
            config = config.group(1) if config else ""

            client_payload = {
                "type": publish_type.value,
                "key": f"{project_link}:{module_name}",
                "config": config,
            }
    else:
        client_payload = {"type": publish_type.value}

    owner, repo = plugin_config.input_config.registry_repository.split("/")
    # GitHub 的缓存一般 2 分钟左右会刷新
    logger.info("准备触发商店列表更新，等待 5 分钟")
    await asyncio.sleep(300)
    # 触发商店列表更新
    await bot.rest.repos.async_create_dispatch_event(
        repo=repo,
        owner=owner,
        event_type="registry_update",
        client_payload=client_payload,  # type: ignore
    )
    logger.info("已触发商店列表更新")
