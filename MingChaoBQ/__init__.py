"""MingChaoBQ 插件入口：先声明 Plugins，再导入业务模块触发触发器注册。"""

from gsuid_core.sv import Plugins

MingChaoBQ = Plugins(
    name="MingChaoBQ",
    prefix=["bq"],
    allow_empty_prefix=False,
)

# 以下导入只为触发 @sv.on_xxx 注册，顺序必须在 Plugins(...) 之后
from . import (  # noqa: E402
    commands as commands,
    whitelist as whitelist,
    mingchao_config as mingchao_config,
)
from .mingchao_help import get_help as get_help  # noqa: E402
