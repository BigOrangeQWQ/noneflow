from functools import cache
from typing import TYPE_CHECKING

import httpx

from src.providers.constants import STORE_ADAPTERS_URL

from .constants import MESSAGE_TRANSLATIONS

if TYPE_CHECKING:
    from pydantic_core import ErrorDetails


def check_pypi(project_link: str) -> bool:
    """检查项目是否存在"""
    url = f"https://pypi.org/pypi/{project_link}/json"
    status_code, _ = check_url(url)
    return status_code == 200


@cache
def check_url(url: str) -> tuple[int, str]:
    """检查网址是否可以访问

    返回状态码，如果报错则返回 -1
    """
    try:
        r = httpx.get(url, follow_redirects=True)
        return r.status_code, ""
    except Exception as e:
        return -1, str(e)


@cache
def get_author_name(author_id: int) -> str:
    """通过作者的ID获取作者名字"""
    url = f"https://api.github.com/user/{author_id}"
    resp = httpx.get(url)
    return resp.json()["login"]


def get_adapters() -> set[str]:
    """获取适配器列表"""
    resp = httpx.get(STORE_ADAPTERS_URL)
    adapters = resp.json()
    return {adapter["module_name"] for adapter in adapters}


def resolve_adapter_name(name: str) -> str:
    """解析适配器名称

    例如：`~onebot.v11` -> `nonebot.adapters.onebot.v11`
    """
    if name.startswith("~"):
        name = "nonebot.adapters." + name[1:]
    return name


def translate_errors(errors: list["ErrorDetails"]) -> list["ErrorDetails"]:
    """翻译 Pydantic 错误信息"""
    new_errors: list["ErrorDetails"] = []
    for error in errors:
        translation = MESSAGE_TRANSLATIONS.get(error["type"])
        if translation:
            ctx = error.get("ctx")
            error["msg"] = translation.format(**ctx) if ctx else translation
        new_errors.append(error)
    return new_errors
