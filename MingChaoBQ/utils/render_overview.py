"""画师 / 角色 / 表情一览图。"""

from pathlib import Path

from PIL import Image

from gsuid_core.help.draw_new_plugin_help import get_new_help

from .help_types import HelpSV, HelpCategory
from .help_assets import (
    PLUGIN_ICON,
    DATA_ICON_DIR,
    load_bg,
    build_footer,
    get_max_width,
    compress_result,
    ensure_icon_dir,
    load_icon_image,
)
from .index_types import Index

COLORS = [
    "#4A90D9",
    "#5CB85C",
    "#E67E22",
    "#9B59B6",
    "#16A085",
    "#E74C3C",
    "#F39C12",
    "#3498DB",
    "#1ABC9C",
    "#8E44AD",
]


def _build_category(
    name: str,
    help_text: str,
    color: str,
    data: list[HelpSV],
    icon: Image.Image | None,
) -> HelpCategory:
    entry = HelpCategory(name=name, help=help_text, desc="", color=color, data=data)
    if icon is not None:
        entry["icon"] = icon
    return entry


async def _render(plugin_name: str, plugin_help: dict[str, HelpCategory], user_pm: int) -> Path:
    # 框架声明的 PluginHelp 与 get_new_help 实际读取的字段不一致，这里给实际字段
    result = await get_new_help(
        plugin_name=plugin_name,
        plugin_info={"": ""},
        plugin_icon=Image.open(PLUGIN_ICON),
        plugin_help=plugin_help,
        plugin_prefix="",
        help_mode="dark",
        banner_bg=load_bg("mcbq_banner_bg"),
        help_bg=load_bg("mcbq_help_bg"),
        footer=build_footer("dark"),
        icon_path=DATA_ICON_DIR,
        column=5,
        pm=user_pm,
        enable_cache=False,
    )
    return compress_result(result, get_max_width())


async def render_artist_overview(index: Index, user_pm: int = 6) -> Path:
    """「画师与角色一览」图：每个画师一张分类卡片，角色作为 item。"""
    ensure_icon_dir()

    plugin_help: dict[str, HelpCategory] = {}
    for i, (artist, chars) in enumerate(index.items()):
        char_names = [c for c in chars if c != "_default"]
        cat_icon = load_icon_image(f"{artist}.png")
        data: list[HelpSV] = []

        if char_names:
            for c in char_names:
                count = sum(len(pics) for pics in chars[c].values())
                item = HelpSV(name=c, eg=f"{count} 张")
                icon = load_icon_image(f"{c}.png")
                if icon is not None:
                    item["icon"] = icon
                data.append(item)
            help_text = f"共 {len(char_names)} 个角色"
        else:
            total = sum(len(pics) for pics in chars.values())
            item = HelpSV(name="（散图）", eg=f"{total} 张未分类")
            if cat_icon is not None:
                item["icon"] = cat_icon
            data.append(item)
            help_text = f"{total} 张散图"

        plugin_help[artist] = _build_category(artist, help_text, COLORS[i % len(COLORS)], data, cat_icon)

    return await _render("鸣潮表情包 · 画师一览", plugin_help, user_pm)
