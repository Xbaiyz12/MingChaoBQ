"""画师 / 角色 / 表情一览图。"""

from pathlib import Path

from PIL import Image

from gsuid_core.help.draw_new_plugin_help import get_new_help

from .help_types import HelpSV, HelpCategory
from .help_assets import (
    PLUGIN_ICON,
    DATA_ICON_DIR,
    load_bg,
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


async def render_char_list(index: Index, char: str, user_pm: int = 6) -> Path:
    """角色表情列表：每个画过该角色的画师一张卡片。"""
    ensure_icon_dir()

    plugin_help: dict[str, HelpCategory] = {}
    color_idx = 0

    for artist, chars in index.items():
        if char not in chars:
            continue
        subcats = chars[char]
        data: list[HelpSV] = []
        total = 0
        for sub_name, pics in subcats.items():
            label = sub_name if sub_name != "_default" else "默认"
            emotions = [p["emotion"] for p in pics]
            total += len(emotions)
            item = HelpSV(name=label, eg="、".join(emotions))
            icon = load_icon_image(f"{char}.png")
            if icon is not None:
                item["icon"] = icon
            data.append(item)

        plugin_help[artist] = _build_category(
            artist,
            f"共 {total} 张",
            COLORS[color_idx % len(COLORS)],
            data,
            load_icon_image(f"{artist}.png"),
        )
        color_idx += 1

    return await _render(f"角色「{char}」表情一览", plugin_help, user_pm)


async def render_one_artist(index: Index, artist: str, user_pm: int = 6) -> Path | None:
    """单个画师的角色列表。画师不存在时返回 None。"""
    if artist not in index:
        return None

    ensure_icon_dir()

    chars = index[artist]
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

    plugin_help = {artist: _build_category(artist, help_text, COLORS[0], data, cat_icon)}
    return await _render(f"画师「{artist}」· 角色一览", plugin_help, user_pm)
