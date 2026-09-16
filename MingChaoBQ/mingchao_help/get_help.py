import json
from pathlib import Path

import aiofiles
from PIL import Image
from gsuid_core.sv import get_plugin_available_prefix
from gsuid_core.help.model import PluginHelp
from gsuid_core.help.draw_new_plugin_help import get_new_help

from ..version import MingChaoBQ_version
from ..utils.help_assets import (
    PLUGIN_ICON,
    DATA_ICON_DIR,
    ensure_icon_dir,
    load_bg,
    load_icon_image,
    compress_result,
    get_max_width,
)

HELP_DATA = Path(__file__).parent / "help.json"

PREFIX = get_plugin_available_prefix("MingChaoBQ")


async def get_help_data() -> dict:
    async with aiofiles.open(HELP_DATA, "rb") as file:
        data = json.loads(await file.read())

    # 把 icon 字符串替换成 Image 对象
    for cat_name, cat_data in data.items():
        if "icon" in cat_data:
            img = load_icon_image(cat_data["icon"])
            if img is not None:
                cat_data["icon"] = img
            else:
                cat_data.pop("icon", None)

        for item in cat_data.get("data", []):
            if "icon" in item:
                img = load_icon_image(item["icon"])
                if img is not None:
                    item["icon"] = img
                else:
                    item.pop("icon", None)

    return data


async def get_help(user_pm: int):
    ensure_icon_dir()

    result = await get_new_help(
        plugin_name="MingChaoBQ",
        plugin_info={f"v{MingChaoBQ_version}": ""},
        plugin_icon=Image.open(PLUGIN_ICON),
        plugin_help=await get_help_data(),
        plugin_prefix=PREFIX,
        help_mode="dark",
        banner_bg=load_bg("mcbq_banner_bg"),
        help_bg=load_bg("mcbq_help_bg"),
        icon_path=DATA_ICON_DIR,
        column=5,
        pm=user_pm,
        enable_cache=False,
    )

    return compress_result(result, get_max_width())