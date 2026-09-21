import json
from pathlib import Path
from collections.abc import Mapping

import aiofiles
from PIL import Image

from gsuid_core.sv import get_plugin_available_prefix
from gsuid_core.help.draw_new_plugin_help import get_new_help

from ..version import MingChaoBQ_version
from ..utils.help_types import HelpSV, HelpCategory
from ..utils.help_assets import (
    PLUGIN_ICON,
    DATA_ICON_DIR,
    load_bg,
    get_max_width,
    compress_result,
    ensure_icon_dir,
    load_icon_image,
)

HELP_DATA = Path(__file__).resolve().parent / "help.json"

PREFIX = get_plugin_available_prefix("MingChaoBQ")


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _build_item(raw: Mapping[object, object]) -> HelpSV:
    item = HelpSV(name=_as_str(raw.get("name")), eg=_as_str(raw.get("eg")))
    icon = load_icon_image(_as_str(raw.get("icon")))
    if icon is not None:
        item["icon"] = icon
    return item


def _build_category(raw: Mapping[object, object]) -> HelpCategory:
    raw_items = raw.get("data")
    items: list[HelpSV] = []
    if isinstance(raw_items, list):
        items = [_build_item(sub) for sub in raw_items if isinstance(sub, dict)]

    entry = HelpCategory(desc=_as_str(raw.get("desc")), data=items)

    name = _as_str(raw.get("name"))
    if name:
        entry["name"] = name
    help_text = _as_str(raw.get("help"))
    if help_text:
        entry["help"] = help_text
    color = _as_str(raw.get("color"))
    if color:
        entry["color"] = color

    pm = raw.get("pm")
    if isinstance(pm, int):
        entry["pm"] = pm

    icon = load_icon_image(_as_str(raw.get("icon")))
    if icon is not None:
        entry["icon"] = icon
    return entry


async def get_help_data() -> dict[str, HelpCategory]:
    async with aiofiles.open(HELP_DATA, "rb") as file:
        raw: object = json.loads(await file.read())

    if not isinstance(raw, dict):
        return {}
    return {
        name: _build_category(data) for name, data in raw.items() if isinstance(name, str) and isinstance(data, dict)
    }


async def get_help(user_pm: int) -> Path:
    ensure_icon_dir()

    # 框架声明的 PluginHelp 与 get_new_help 实际读取的字段不一致，这里给实际字段
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
