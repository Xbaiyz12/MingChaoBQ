from gsuid_core.sv import Plugins

MingChaoBQ = Plugins(
    name="MingChaoBQ",
    prefix=["bq"],
    allow_empty_prefix=False,
)

# 关键：导入所有包含 SV 和 on_command 的模块
from . import commands
from . import whitelist
from .mingchao_help import get_help
from . import mingchao_config