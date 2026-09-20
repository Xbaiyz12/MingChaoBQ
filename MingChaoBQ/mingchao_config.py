import json

from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT

# 配置文件的真实路径
CONFIG_PATH = get_res_path("MingChaoBQ") / "config.json"

# 全局唯一实例：注册到 GsCore，供网页控制台展示和管理
_mcbq_config = StringConfig("MingChaoBQ", CONFIG_PATH, CONFIG_DEFAULT)


def get_config(key: str):
    """
    读取配置项。每次都从磁盘读，保证网页控制台改完后立即生效。
    磁盘读失败则回退到 StringConfig 内存值。
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get(key)
        if isinstance(raw, dict) and "data" in raw:
            return raw["data"]
    except Exception:
        pass

    try:
        return _mcbq_config.get_config(key).data
    except Exception:
        if key in CONFIG_DEFAULT:
            return CONFIG_DEFAULT[key].data
        return None


def set_config(key: str, value):
    """写入配置项（同时更新内存和磁盘）"""
    _mcbq_config.set_config(key, value)