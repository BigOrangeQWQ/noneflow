from typing import Any

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


class StorePlugin(BaseModel):
    """NoneBot 仓库中的插件数据"""

    module_name: str
    project_link: str
    author: str
    tags: list[Any]
    is_official: bool


class Plugin(BaseModel):
    """NoneBot 商店插件数据"""

    module_name: str
    project_link: str
    name: str
    desc: str
    author: str
    homepage: str
    tags: list[Any]
    is_official: bool
    type: str
    supported_adapters: list[str] | None
    valid: bool
    time: str
    version: str
    skip_test: bool = Field(default=False)


class Metadata(BaseModel):
    """插件元数据"""

    name: str
    description: str
    homepage: str
    type: str
    supported_adapters: list[str] | None


class DockerTestResult(BaseModel):
    version: str
    time: str = Field(
        default_factory=lambda: datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    )
    metadata: Metadata | None
    output: list[str]
    config: str
    status: bool
    is_run: bool


class TestResult(BaseModel):
    version: list[str]
    valid: bool
    time: str = Field(
        default_factory=lambda: datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    )