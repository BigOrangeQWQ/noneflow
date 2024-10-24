import json
from pathlib import Path

from inline_snapshot import snapshot
import pytest
from pytest_mock import MockerFixture
from respx import MockRouter

from src.providers.constants import (
    REGISTRY_PLUGIN_CONFIG_URL,
    REGISTRY_PLUGINS_URL,
    REGISTRY_RESULTS_URL,
    STORE_ADAPTERS_URL,
    STORE_BOTS_URL,
    STORE_DRIVERS_URL,
    STORE_PLUGINS_URL,
)


def load_json(name: str) -> dict:
    path = Path(__file__).parent / "store" / f"{name}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mocked_store_data(
    tmp_path: Path,
    mocker: MockerFixture,
    mocked_api: MockRouter,
) -> dict[str, Path]:
    plugin_test_path = tmp_path / "plugin_test"
    plugin_test_path.mkdir()

    paths = {
        "results": plugin_test_path / "results.json",
        "adapters": plugin_test_path / "adapters.json",
        "bots": plugin_test_path / "bots.json",
        "drivers": plugin_test_path / "drivers.json",
        "plugins": plugin_test_path / "plugins.json",
        "plugin_configs": plugin_test_path / "plugin_configs.json",
    }

    mocker.patch(
        "src.providers.store_test.store.RESULTS_PATH",
        paths["results"],
    )
    mocker.patch(
        "src.providers.store_test.store.ADAPTERS_PATH",
        paths["adapters"],
    )
    mocker.patch("src.providers.store_test.store.BOTS_PATH", paths["bots"])
    mocker.patch(
        "src.providers.store_test.store.DRIVERS_PATH",
        paths["drivers"],
    )
    mocker.patch(
        "src.providers.store_test.store.PLUGINS_PATH",
        paths["plugins"],
    )
    mocker.patch(
        "src.providers.store_test.store.PLUGIN_CONFIG_PATH",
        paths["plugin_configs"],
    )

    mocked_api.get(REGISTRY_RESULTS_URL).respond(json=load_json("registry_results"))
    mocked_api.get(REGISTRY_PLUGINS_URL).respond(json=load_json("registry_plugins"))
    mocked_api.get(STORE_ADAPTERS_URL).respond(json=load_json("store_adapters"))
    mocked_api.get(STORE_BOTS_URL).respond(json=load_json("store_bots"))
    mocked_api.get(STORE_DRIVERS_URL).respond(json=load_json("store_drivers"))
    mocked_api.get(STORE_PLUGINS_URL).respond(json=load_json("store_plugins"))
    mocked_api.get(REGISTRY_PLUGIN_CONFIG_URL).respond(json=load_json("plugin_configs"))

    return paths


async def test_store_test(
    mocked_store_data: dict[str, Path], mocked_api: MockRouter, mocker: MockerFixture
) -> None:
    """验证插件信息

    第一个插件因为版本号无变化跳过
    第二插件验证通过
    因为 limit=1 所以只测试了一个插件，第三个插件未测试
    """
    from src.providers.store_test.store import (
        Plugin,
        StoreTest,
        TestResult,
        StorePlugin,
    )

    mocked_validate_plugin = mocker.patch(
        "src.providers.store_test.store.validate_plugin"
    )
    mocked_validate_plugin.return_value = (
        TestResult(
            time="2023-08-28T00:00:00.000000+08:00",
            version="1.0.0",
            config="",
            results={
                "load": True,
                "metadata": True,
                "validation": True,
            },
            outputs={
                "load": "output",
                "metadata": {
                    "name": "帮助",
                    "description": "获取插件帮助信息",
                    "usage": "获取插件列表\n/help\n获取插件树\n/help -t\n/help --tree\n获取某个插件的帮助\n/help 插件名\n获取某个插件的树\n/help --tree 插件名\n",
                    "type": "application",
                    "homepage": "https://nonebot.dev/",
                    "supported_adapters": None,
                },
                "validation": None,
            },
        ),
        Plugin(
            name="帮助",
            module_name="module_name",
            author="author",
            author_id=1,
            version="0.3.0",
            desc="获取插件帮助信息",
            homepage="https://nonebot.dev/",
            project_link="project_link",
            tags=[],
            supported_adapters=None,
            type="application",
            time="2023-08-28T00:00:00.000000+08:00",
            is_official=True,
            valid=True,
            skip_test=False,
        ),
    )

    test = StoreTest()
    await test.run(1, False)

    mocked_validate_plugin.assert_called_once_with(
        plugin=StorePlugin(
            tags=[],
            module_name="nonebot_plugin_treehelp",
            project_link="nonebot-plugin-treehelp",
            author_id=1,
            is_official=False,
        ),
        config="TEST_CONFIG=true",
        skip_test=False,
        plugin_data=None,
        previous_plugin=Plugin(
            tags=[],
            module_name="nonebot_plugin_treehelp",
            project_link="nonebot-plugin-treehelp",
            name="帮助",
            desc="获取插件帮助信息",
            author="he0119",
            author_id=1,
            homepage="https://github.com/he0119/nonebot-plugin-treehelp",
            is_official=False,
            type="application",
            supported_adapters=None,
            valid=True,
            time="2023-06-22 12:10:18",
            version="0.0.1",
            skip_test=False,
        ),
    )
    assert mocked_api["project_link_treehelp"].called
    assert mocked_api["project_link_datastore"].called

    assert (
        mocked_store_data["results"].read_text(encoding="utf-8")
        == snapshot(
            '{"nonebot-plugin-datastore:nonebot_plugin_datastore":{"time":"2023-06-26T22:08:18.945584+08:00","config":"","version":"1.0.0","test_env":null,"results":{"validation":true,"load":true,"metadata":true},"outputs":{"validation":"通过","load":"datastore","metadata":{"name":"数据存储","description":"NoneBot 数据存储插件","usage":"请参考文档","type":"library","homepage":"https://github.com/he0119/nonebot-plugin-datastore","supported_adapters":null}}},"nonebot-plugin-treehelp:nonebot_plugin_treehelp":{"time":"2023-08-28T00:00:00.000000+08:00","config":"","version":"1.0.0","test_env":null,"results":{"load":true,"metadata":true,"validation":true},"outputs":{"load":"output","metadata":{"name":"帮助","description":"获取插件帮助信息","usage":"获取插件列表\\n/help\\n获取插件树\\n/help -t\\n/help --tree\\n获取某个插件的帮助\\n/help 插件名\\n获取某个插件的树\\n/help --tree 插件名\\n","type":"application","homepage":"https://nonebot.dev/","supported_adapters":null},"validation":null}}}'
        )
        # == '{"nonebot-plugin-datastore:nonebot_plugin_datastore":{"time":"2023-06-26T22:08:18.945584+08:00","version":"1.0.0","results":{"validation":true,"load":true,"metadata":true},"inputs":{"config":""},"outputs":{"validation":"通过","load":"datastore","metadata":{"name":"数据存储","description":"NoneBot 数据存储插件","usage":"请参考文档","type":"library","homepage":"https://github.com/he0119/nonebot-plugin-datastore","supported_adapters":null}}},"nonebot-plugin-treehelp:nonebot_plugin_treehelp":{"time":"2023-08-28T00:00:00.000000+08:00","version":"1.0.0","inputs":{"config":""},"results":{"load":true,"metadata":true,"validation":true},"outputs":{"load":"output","metadata":{"name":"帮助","description":"获取插件帮助信息","usage":"获取插件列表\\n/help\\n获取插件树\\n/help -t\\n/help --tree\\n获取某个插件的帮助\\n/help 插件名\\n获取某个插件的树\\n/help --tree 插件名\\n","type":"application","homepage":"https://nonebot.dev/","supported_adapters":null},"validation":null}}}'
    )
    assert mocked_store_data["adapters"].read_text(encoding="utf-8") == snapshot(
        '[{"module_name":"nonebot.adapters.onebot.v11","project_link":"nonebot-adapter-onebot","name":"OneBot V11","desc":"OneBot V11 协议","author":"yanyongyu","homepage":"https://onebot.adapters.nonebot.dev/","tags":[],"is_official":true}]'
    )
    assert mocked_store_data["bots"].read_text(encoding="utf-8") == snapshot(
        '[{"name":"CoolQBot","desc":"基于 NoneBot2 的聊天机器人","author":"he0119","homepage":"https://github.com/he0119/CoolQBot","tags":[],"is_official":false}]'
    )
    assert mocked_store_data["drivers"].read_text(encoding="utf-8") == snapshot(
        '[{"module_name":"~none","project_link":"","name":"None","desc":"None 驱动器","author":"yanyongyu","homepage":"/docs/advanced/driver","tags":[],"is_official":true},{"module_name":"~fastapi","project_link":"nonebot2[fastapi]","name":"FastAPI","desc":"FastAPI 驱动器","author":"yanyongyu","homepage":"/docs/advanced/driver","tags":[],"is_official":true}]'
    )
    assert mocked_store_data["plugins"].read_text(encoding="utf-8") == snapshot(
        '[{"tags":[],"module_name":"nonebot_plugin_datastore","project_link":"nonebot-plugin-datastore","name":"数据存储","desc":"NoneBot 数据存储插件","author":"he0119","author_id":1,"homepage":"https://github.com/he0119/nonebot-plugin-datastore","is_official":false,"type":"library","supported_adapters":null,"valid":true,"time":"2023-06-22 11:58:18","version":"0.0.1","skip_test":false},{"tags":[],"module_name":"module_name","project_link":"project_link","name":"帮助","desc":"获取插件帮助信息","author":"author","author_id":1,"homepage":"https://nonebot.dev/","is_official":true,"type":"application","supported_adapters":null,"valid":true,"time":"2023-08-28T00:00:00.000000+08:00","version":"0.3.0","skip_test":false}]'
    )


async def test_store_test_with_key(
    mocked_store_data: dict[str, Path], mocked_api: MockRouter, mocker: MockerFixture
) -> None:
    """测试指定插件，因为版本更新正常测试"""
    from src.providers.store_test.store import StoreTest, StorePlugin, Plugin

    mocked_validate_plugin = mocker.patch(
        "src.providers.store_test.store.validate_plugin"
    )
    mocked_validate_plugin.return_value = ({}, {})

    test = StoreTest()
    await test.run_single_plugin(key="nonebot-plugin-treehelp:nonebot_plugin_treehelp")

    mocked_validate_plugin.assert_called_once_with(
        plugin=StorePlugin(
            tags=[],
            module_name="nonebot_plugin_treehelp",
            project_link="nonebot-plugin-treehelp",
            author_id=1,
            is_official=False,
        ),
        config="TEST_CONFIG=true",
        skip_test=False,
        plugin_data=None,
        previous_plugin=Plugin(
            tags=[],
            module_name="nonebot_plugin_treehelp",
            project_link="nonebot-plugin-treehelp",
            name="帮助",
            desc="获取插件帮助信息",
            author="he0119",
            author_id=1,
            homepage="https://github.com/he0119/nonebot-plugin-treehelp",
            is_official=False,
            type="application",
            supported_adapters=None,
            valid=True,
            time="2023-06-22 12:10:18",
            version="0.0.1",
            skip_test=False,
        ),
    )
    assert mocked_api["project_link_treehelp"].called
    assert not mocked_api["project_link_datastore"].called


async def test_store_test_with_key_skip(
    mocked_store_data: dict[str, Path], mocked_api: MockRouter, mocker: MockerFixture
) -> None:
    """测试指定插件，因为版本未更新跳过测试"""
    from src.providers.store_test.store import StoreTest

    mocked_validate_plugin = mocker.patch(
        "src.providers.store_test.store.validate_plugin"
    )

    test = StoreTest()
    await test.run_single_plugin(
        key="nonebot-plugin-datastore:nonebot_plugin_datastore"
    )

    mocked_validate_plugin.assert_not_called()
    assert not mocked_api["project_link_treehelp"].called
    assert mocked_api["project_link_datastore"].called


async def test_store_test_with_key_not_in_previous(
    mocked_store_data: dict[str, Path], mocked_api: MockRouter, mocker: MockerFixture
) -> None:
    """测试指定插件，因为从未测试过，正常测试"""
    from src.providers.store_test.store import StoreTest, StorePlugin

    mocked_validate_plugin = mocker.patch(
        "src.providers.store_test.store.validate_plugin"
    )
    mocked_validate_plugin.return_value = ({}, {})

    test = StoreTest()
    await test.run_single_plugin(
        key="nonebot-plugin-wordcloud:nonebot_plugin_wordcloud"
    )

    mocked_validate_plugin.assert_called_once_with(
        plugin=StorePlugin(
            tags=[],
            module_name="nonebot_plugin_wordcloud",
            project_link="nonebot-plugin-wordcloud",
            author_id=1,
            is_official=False,
        ),
        config="",
        skip_test=False,
        plugin_data=None,
        previous_plugin=None,
    )

    # 不需要判断版本号
    assert not mocked_api["project_link_wordcloud"].called
    assert not mocked_api["project_link_treehelp"].called
    assert not mocked_api["project_link_datastore"].called


async def test_store_test_raise(
    mocked_store_data: dict[str, Path], mocked_api: MockRouter, mocker: MockerFixture
):
    """测试插件，但是测试过程中报错

    第一个插件因为版本号无变化跳过
    第二插件测试中报错跳过
    第三个插件测试中也报错

    最后数据没有变化
    """
    from src.providers.store_test.store import StoreTest, StorePlugin, Plugin

    mocked_validate_plugin = mocker.patch(
        "src.providers.store_test.store.validate_plugin"
    )
    mocked_validate_plugin.side_effect = Exception

    test = StoreTest()
    await test.run(limit=1)

    mocked_validate_plugin.assert_has_calls(
        [
            mocker.call(
                plugin=StorePlugin(
                    tags=[],
                    module_name="nonebot_plugin_treehelp",
                    project_link="nonebot-plugin-treehelp",
                    author_id=1,
                    is_official=False,
                ),
                config="TEST_CONFIG=true",
                skip_test=False,
                plugin_data=None,
                previous_plugin=Plugin(
                    tags=[],
                    module_name="nonebot_plugin_treehelp",
                    project_link="nonebot-plugin-treehelp",
                    name="帮助",
                    desc="获取插件帮助信息",
                    author="he0119",
                    author_id=1,
                    homepage="https://github.com/he0119/nonebot-plugin-treehelp",
                    is_official=False,
                    type="application",
                    supported_adapters=None,
                    valid=True,
                    time="2023-06-22 12:10:18",
                    version="0.0.1",
                    skip_test=False,
                ),
            ),
            mocker.call(
                plugin=StorePlugin(
                    tags=[],
                    module_name="nonebot_plugin_wordcloud",
                    project_link="nonebot-plugin-wordcloud",
                    author_id=1,
                    is_official=False,
                ),
                config="",
                skip_test=False,
                plugin_data=None,
                previous_plugin=None,
            ),  # type: ignore
        ],
    )

    # 数据没有更新，只是被压缩
    assert mocked_store_data["results"].read_text(encoding="utf-8") == snapshot(
        '{"nonebot-plugin-datastore:nonebot_plugin_datastore":{"time":"2023-06-26T22:08:18.945584+08:00","config":"","version":"1.0.0","test_env":null,"results":{"validation":true,"load":true,"metadata":true},"outputs":{"validation":"通过","load":"datastore","metadata":{"name":"数据存储","description":"NoneBot 数据存储插件","usage":"请参考文档","type":"library","homepage":"https://github.com/he0119/nonebot-plugin-datastore","supported_adapters":null}}},"nonebot-plugin-treehelp:nonebot_plugin_treehelp":{"time":"2023-06-26T22:20:41.833311+08:00","config":"","version":"0.3.0","test_env":null,"results":{"validation":true,"load":true,"metadata":true},"outputs":{"validation":"通过","load":"treehelp","metadata":{"name":"帮助","description":"获取插件帮助信息","usage":"获取插件列表\\n/help\\n获取插件树\\n/help -t\\n/help --tree\\n获取某个插件的帮助\\n/help 插件名\\n获取某个插件的树\\n/help --tree 插件名\\n","type":"application","homepage":"https://github.com/he0119/nonebot-plugin-treehelp","supported_adapters":null}}}}'
    )
    assert mocked_store_data["adapters"].read_text(encoding="utf-8") == snapshot(
        '[{"module_name":"nonebot.adapters.onebot.v11","project_link":"nonebot-adapter-onebot","name":"OneBot V11","desc":"OneBot V11 协议","author":"yanyongyu","homepage":"https://onebot.adapters.nonebot.dev/","tags":[],"is_official":true}]'
    )
    assert mocked_store_data["bots"].read_text(encoding="utf-8") == snapshot(
        '[{"name":"CoolQBot","desc":"基于 NoneBot2 的聊天机器人","author":"he0119","homepage":"https://github.com/he0119/CoolQBot","tags":[],"is_official":false}]'
    )
    assert mocked_store_data["drivers"].read_text(encoding="utf-8") == snapshot(
        '[{"module_name":"~none","project_link":"","name":"None","desc":"None 驱动器","author":"yanyongyu","homepage":"/docs/advanced/driver","tags":[],"is_official":true},{"module_name":"~fastapi","project_link":"nonebot2[fastapi]","name":"FastAPI","desc":"FastAPI 驱动器","author":"yanyongyu","homepage":"/docs/advanced/driver","tags":[],"is_official":true}]'
    )
    assert mocked_store_data["plugins"].read_text(encoding="utf-8") == snapshot(
        '[{"tags":[],"module_name":"nonebot_plugin_datastore","project_link":"nonebot-plugin-datastore","name":"数据存储","desc":"NoneBot 数据存储插件","author":"he0119","author_id":1,"homepage":"https://github.com/he0119/nonebot-plugin-datastore","is_official":false,"type":"library","supported_adapters":null,"valid":true,"time":"2023-06-22 11:58:18","version":"0.0.1","skip_test":false},{"tags":[],"module_name":"nonebot_plugin_treehelp","project_link":"nonebot-plugin-treehelp","name":"帮助","desc":"获取插件帮助信息","author":"he0119","author_id":1,"homepage":"https://github.com/he0119/nonebot-plugin-treehelp","is_official":false,"type":"application","supported_adapters":null,"valid":true,"time":"2023-06-22 12:10:18","version":"0.0.1","skip_test":false}]'
    )


async def test_store_test_with_key_raise(
    mocked_store_data: dict[str, Path], mocked_api: MockRouter, mocker: MockerFixture
):
    """测试指定插件，但是测试过程中报错"""
    from src.providers.store_test.store import StoreTest, StorePlugin

    mocked_validate_plugin = mocker.patch(
        "src.providers.store_test.store.validate_plugin"
    )
    mocked_validate_plugin.side_effect = Exception

    test = StoreTest()
    await test.run_single_plugin(
        key="nonebot-plugin-wordcloud:nonebot_plugin_wordcloud"
    )

    mocked_validate_plugin.assert_called_once_with(
        plugin=StorePlugin(
            module_name="nonebot_plugin_wordcloud",
            project_link="nonebot-plugin-wordcloud",
            author_id=1,
            tags=[],
            is_official=False,
        ),
        config="",
        skip_test=False,
        plugin_data=None,
        previous_plugin=None,
    )

    # 数据没有更新，只是被压缩
    assert mocked_store_data["results"].read_text(encoding="utf-8") == snapshot(
        '{"nonebot-plugin-datastore:nonebot_plugin_datastore":{"time":"2023-06-26T22:08:18.945584+08:00","config":"","version":"1.0.0","test_env":null,"results":{"validation":true,"load":true,"metadata":true},"outputs":{"validation":"通过","load":"datastore","metadata":{"name":"数据存储","description":"NoneBot 数据存储插件","usage":"请参考文档","type":"library","homepage":"https://github.com/he0119/nonebot-plugin-datastore","supported_adapters":null}}},"nonebot-plugin-treehelp:nonebot_plugin_treehelp":{"time":"2023-06-26T22:20:41.833311+08:00","config":"","version":"0.3.0","test_env":null,"results":{"validation":true,"load":true,"metadata":true},"outputs":{"validation":"通过","load":"treehelp","metadata":{"name":"帮助","description":"获取插件帮助信息","usage":"获取插件列表\\n/help\\n获取插件树\\n/help -t\\n/help --tree\\n获取某个插件的帮助\\n/help 插件名\\n获取某个插件的树\\n/help --tree 插件名\\n","type":"application","homepage":"https://github.com/he0119/nonebot-plugin-treehelp","supported_adapters":null}}}}'
    )
    assert mocked_store_data["adapters"].read_text(encoding="utf-8") == snapshot(
        '[{"module_name":"nonebot.adapters.onebot.v11","project_link":"nonebot-adapter-onebot","name":"OneBot V11","desc":"OneBot V11 协议","author":"yanyongyu","homepage":"https://onebot.adapters.nonebot.dev/","tags":[],"is_official":true}]'
    )
    assert mocked_store_data["bots"].read_text(encoding="utf-8") == snapshot(
        '[{"name":"CoolQBot","desc":"基于 NoneBot2 的聊天机器人","author":"he0119","homepage":"https://github.com/he0119/CoolQBot","tags":[],"is_official":false}]'
    )
    assert mocked_store_data["drivers"].read_text(encoding="utf-8") == snapshot(
        '[{"module_name":"~none","project_link":"","name":"None","desc":"None 驱动器","author":"yanyongyu","homepage":"/docs/advanced/driver","tags":[],"is_official":true},{"module_name":"~fastapi","project_link":"nonebot2[fastapi]","name":"FastAPI","desc":"FastAPI 驱动器","author":"yanyongyu","homepage":"/docs/advanced/driver","tags":[],"is_official":true}]'
    )
    assert mocked_store_data["plugins"].read_text(encoding="utf-8") == snapshot(
        '[{"tags":[],"module_name":"nonebot_plugin_datastore","project_link":"nonebot-plugin-datastore","name":"数据存储","desc":"NoneBot 数据存储插件","author":"he0119","author_id":1,"homepage":"https://github.com/he0119/nonebot-plugin-datastore","is_official":false,"type":"library","supported_adapters":null,"valid":true,"time":"2023-06-22 11:58:18","version":"0.0.1","skip_test":false},{"tags":[],"module_name":"nonebot_plugin_treehelp","project_link":"nonebot-plugin-treehelp","name":"帮助","desc":"获取插件帮助信息","author":"he0119","author_id":1,"homepage":"https://github.com/he0119/nonebot-plugin-treehelp","is_official":false,"type":"application","supported_adapters":null,"valid":true,"time":"2023-06-22 12:10:18","version":"0.0.1","skip_test":false}]'
    )
