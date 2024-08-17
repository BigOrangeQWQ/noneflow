from typing import Any, Literal, TypedDict


class StorePlugin(TypedDict):
    """NoneBot 仓库中的插件数据"""

    module_name: str
    project_link: str
    author: str
    tags: list[Any]
    is_official: bool


class Plugin(TypedDict):
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
    skip_test: bool


class Metadata(TypedDict):
    """插件元数据"""

    name: str
    description: str
    homepage: str
    type: str
    supported_adapters: list[str]


class TestResult(TypedDict):
    time: str
    config: str
    version: str | None
    test_env: dict[str, bool]
    results: dict[Literal["validation", "load", "metadata"], bool]
    outputs: dict[Literal["validation", "load", "metadata"], Any]


class DockerTestResult(TypedDict):
    """Docker 测试结果"""

    run: bool  # 是否运行
    load: bool  # 是否加载成功
    version: str | None
    config: str
    # 测试环境 python==3.10 pytest==6.2.5 nonebot2==2.0.0a1 ...
    test_env: str
    metadata: Metadata | None
    outputs: list[str]
