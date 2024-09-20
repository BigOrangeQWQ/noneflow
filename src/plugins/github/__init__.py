from pathlib import Path

import nonebot

from .config import Config

# 加载子插件
sub_plugins = nonebot.load_plugins(str((Path(__file__).parent / "plugins").resolve()))

plugin_config = Config.model_validate(dict(nonebot.get_driver().config))
