# type: ignore
import json
from collections import OrderedDict

from github.Issue import Issue
from pytest_mock import MockerFixture

from src.models import PluginPublishInfo


def generate_issue_body(
    name: str = "name",
    desc: str = "desc",
    module_name: str = "module_name",
    project_link: str = "project_link",
    homepage: str = "https://v2.nonebot.dev",
    tags: list = [{"label": "test", "color": "#ffffff"}],
):
    return f"""**插件名称：**\n\n{name}\n\n**插件功能：**\n\n{desc}\n\n**PyPI 项目名：**\n\n{project_link}\n\n**插件 import 包名：**\n\n{module_name}\n\n**插件项目仓库/主页链接：**\n\n{homepage}\n\n**标签：**\n\n{json.dumps(tags)}"""


def mocked_requests_get(url: str):
    class MockResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code

    if url == "https://pypi.org/pypi/project_link/json":
        return MockResponse(200)
    if url == "https://v2.nonebot.dev":
        return MockResponse(200)

    return MockResponse(404)


def test_check_load(mocker: MockerFixture) -> None:
    """测试检查插件加载情况"""
    mock_requests = mocker.patch("requests.get", side_effect=mocked_requests_get)
    mock_issue: Issue = mocker.MagicMock()
    mock_issue.body = generate_issue_body()
    mock_issue.user.login = "author"
    mock_subprocess_run = mocker.patch("subprocess.run")

    info = PluginPublishInfo.from_issue(mock_issue)

    assert OrderedDict(info.dict()) == OrderedDict(
        project_link="project_link",
        module_name="module_name",
        name="name",
        desc="desc",
        author="author",
        homepage="https://v2.nonebot.dev",
        tags=[{"label": "test", "color": "#ffffff"}],
        is_official=False,
    )
    calls = [
        mocker.call("https://pypi.org/pypi/project_link/json"),
        mocker.call("https://v2.nonebot.dev"),
    ]
    mock_requests.assert_has_calls(calls)
    assert mock_subprocess_run.call_count == 3