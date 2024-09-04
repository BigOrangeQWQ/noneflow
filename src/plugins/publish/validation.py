import json
import re
from typing import TYPE_CHECKING, Any

from nonebot import logger
from src.utils.validation import (
    PublishType,
    ValidationDict,
    extract_publish_info_from_issue,
    validate_info,
)
from src.utils.constants import DOCKER_IMAGES
from src.utils.docker_test import DockerPluginTest
from src.utils.store_test.models import DockerTestResult, Metadata

from .config import plugin_config
from .constants import (
    ADAPTER_DESC_PATTERN,
    ADAPTER_HOMEPAGE_PATTERN,
    ADAPTER_MODULE_NAME_PATTERN,
    ADAPTER_NAME_PATTERN,
    BOT_DESC_PATTERN,
    BOT_HOMEPAGE_PATTERN,
    BOT_NAME_PATTERN,
    PLUGIN_CONFIG_PATTERN,
    PLUGIN_DESC_PATTERN,
    PLUGIN_HOMEPAGE_PATTERN,
    PLUGIN_MODULE_NAME_PATTERN,
    PLUGIN_NAME_PATTERN,
    PLUGIN_SUPPORTED_ADAPTERS_PATTERN,
    PLUGIN_TYPE_PATTERN,
    PROJECT_LINK_PATTERN,
    TAGS_PATTERN,
)

if TYPE_CHECKING:
    from githubkit.rest import Issue


def strip_ansi(text: str | None) -> str:
    """去除 ANSI 转义字符"""
    if not text:
        return ""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


async def validate_plugin_info_from_issue(issue: "Issue") -> ValidationDict:
    """从议题中提取插件信息"""
    body = issue.body if issue.body else ""
    author = issue.user.id if issue.user else ""
    author_id = issue.user.id if issue.user else None

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
            "load": plugin_test_result.load,
            "result": plugin_test_result,
            "output": plugin_test_output,
            "metadata": plugin_test_metadata,
            "previous_data": previous_data,
            "author": author,
            "author_id": author_id,
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
        validate_data.data.get("metadata") is None
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


async def validate_adapter_info_from_issue(issue: "Issue") -> ValidationDict:
    """从议题中提取适配器信息"""
    body = issue.body if issue.body else ""
    author = issue.user.login if issue.user else ""
    author_id = issue.user.id if issue.user else None
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
    raw_data["author_id"] = author_id
    raw_data["previous_data"] = previous_data

    return validate_info(PublishType.ADAPTER, raw_data)


async def validate_bot_info_from_issue(issue: "Issue") -> ValidationDict:
    """从议题中提取机器人信息"""
    body = issue.body if issue.body else ""
    author = issue.user.login if issue.user else ""
    author_id = issue.user.id if issue.user else None
    raw_data: dict[str, Any] = extract_publish_info_from_issue(
        {
            "name": BOT_NAME_PATTERN,
            "desc": BOT_DESC_PATTERN,
            "homepage": BOT_HOMEPAGE_PATTERN,
            "tags": TAGS_PATTERN,
        },
        body,
    )
    raw_data["author"] = author
    raw_data["author_id"] = author_id

    return validate_info(PublishType.BOT, raw_data)
