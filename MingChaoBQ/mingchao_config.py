"""MingChaoBQ 配置：包装 StringConfig，对外只暴露带类型守卫的访问器。"""

from typing import Literal
from pathlib import Path

from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT

# 配置文件的真实路径
CONFIG_PATH: Path = get_res_path("MingChaoBQ") / "config.json"

# 全局唯一实例：注册到 GsCore，供网页控制台展示和管理
# StringConfig 按 name 复用同一个对象，网页控制台改的就是它，所以内存值与磁盘同步
_mcbq_config = StringConfig("MingChaoBQ", CONFIG_PATH, CONFIG_DEFAULT)

BoolKey = Literal[
    "mcbq_enable",
    "mcbq_whitelist_enable",
    "mcbq_api_enable",
    "mcbq_api_save_local",
    "mcbq_poke_enable",
]

StrKey = Literal[
    "mcbq_banner_bg",
    "mcbq_help_bg",
    "mcbq_image_max_width",
    "mcbq_api_base",
    "mcbq_api_token",
    "mcbq_api_random_path",
    "mcbq_api_character_param",
    "mcbq_poke_set_pm",
]

ListKey = Literal[
    "mcbq_whitelist",
    "mcbq_blacklist",
    "mcbq_char_alias",
    "mcbq_poke_group_roles",
]

ConfigKey = BoolKey | StrKey | ListKey


def _raw(key: ConfigKey) -> object:
    """取配置原始值。框架的 get_config 返回 Any，这里立刻收敛成 object 阻断 Any 传播。"""
    value: object = _mcbq_config.get_config(key).data
    return value


def get_bool(key: BoolKey) -> bool:
    value = _raw(key)
    return value if isinstance(value, bool) else False


def get_str(key: StrKey) -> str:
    value = _raw(key)
    return value if isinstance(value, str) else ""


def get_int(key: StrKey, default: int) -> int:
    """配置存的是字符串，网页控制台可能被填成任意内容，非法值回退默认。"""
    raw = get_str(key).strip()
    if raw.isdigit():
        return int(raw)
    return default


def get_str_list(key: ListKey) -> list[str]:
    value = _raw(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def set_config(key: ConfigKey, value: bool | str | list[str]) -> bool:
    """写入并落盘。框架按类型是否一致决定成败，失败要报出来而不是静默丢。"""
    ok = _mcbq_config.set_config(key, value)
    if not ok:
        logger.warning(f"[MingChaoBQ·配置] 写入失败（类型不匹配）: {key}={value!r}")
    return ok
