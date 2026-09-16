from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig
from .config_default import CONFIG_DEFAULT

CONFIG_PATH = get_res_path("MingChaoBQ") / "config.json"
_mcbq_config = StringConfig("MingChaoBQ", CONFIG_PATH, CONFIG_DEFAULT)


def get_config(key: str):
    return _mcbq_config.get_config(key).data


def set_config(key: str, value):
    _mcbq_config.set_config(key, value)