from PIL import Image
from gsuid_core.help.draw_new_plugin_help import get_new_help

from .help_assets import (
    PLUGIN_ICON,
    DATA_ICON_DIR,
    ensure_icon_dir,
    load_bg,
    load_icon_image,
    compress_result,
    get_max_width,
)

COLORS = [
    "#4A90D9", "#5CB85C", "#E67E22", "#9B59B6",
    "#16A085", "#E74C3C", "#F39C12", "#3498DB",
    "#1ABC9C", "#8E44AD",
]


async def render_artist_overview(index: dict, user_pm: int = 6):
    """「画师与角色一览」图：每个画师一张分类卡片，角色作为 item。"""
    ensure_icon_dir()

    plugin_help = {}
    for i, (artist, chars) in enumerate(index.items()):
        char_names = [c for c in chars.keys() if c != "_default"]

        # 分类卡片图标（用画师名.png）
        cat_icon = load_icon_image(f"{artist}.png")

        if char_names:
            data = []
            for c in char_names:
                count = sum(len(pics) for pics in chars[c].values())
                item = {"name": c, "eg": f"{count} 张"}
                icon_img = load_icon_image(f"{c}.png")
                if icon_img is not None:
                    item["icon"] = icon_img
                data.append(item)
            help_text = f"共 {len(char_names)} 个角色"
        else:
            total = sum(len(pics) for pics in chars.values())
            item = {"name": "（散图）", "eg": f"{total} 张未分类"}
            icon_img = load_icon_image(f"{artist}.png")
            if icon_img is not None:
                item["icon"] = icon_img
            data = [item]
            help_text = f"{total} 张散图"

        entry = {
            "name": artist,
            "help": help_text,
            "desc": "",
            "color": COLORS[i % len(COLORS)],
            "data": data,
        }
        if cat_icon is not None:
            entry["icon"] = cat_icon
        plugin_help[artist] = entry

    result = await get_new_help(
        plugin_name="鸣潮表情包 · 画师一览",
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


async def render_char_list(index: dict, char: str, user_pm: int = 6):
    """角色表情列表：每个画过该角色的画师一张卡片。"""
    ensure_icon_dir()

    plugin_help = {}
    color_idx = 0

    for artist, chars in index.items():
        if char not in chars:
            continue
        subcats = chars[char]
        data = []
        total = 0
        for sub_name, pics in subcats.items():
            label = sub_name if sub_name != "_default" else "默认"
            emotions = [p["emotion"] for p in pics]
            total += len(emotions)
            item = {"name": label, "eg": "、".join(emotions)}
            icon_img = load_icon_image(f"{char}.png")
            if icon_img is not None:
                item["icon"] = icon_img
            data.append(item)

        cat_icon = load_icon_image(f"{artist}.png")
        entry = {
            "name": artist,
            "help": f"共 {total} 张",
            "desc": "",
            "color": COLORS[color_idx % len(COLORS)],
            "data": data,
        }
        if cat_icon is not None:
            entry["icon"] = cat_icon
        plugin_help[artist] = entry
        color_idx += 1

    result = await get_new_help(
        plugin_name=f"角色「{char}」表情一览",
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


async def render_one_artist(index: dict, artist: str, user_pm: int = 6):
    """单个画师的角色列表。"""
    if artist not in index:
        return None

    ensure_icon_dir()

    chars = index[artist]
    char_names = [c for c in chars.keys() if c != "_default"]
    cat_icon = load_icon_image(f"{artist}.png")

    if char_names:
        data = []
        for c in char_names:
            count = sum(len(pics) for pics in chars[c].values())
            item = {"name": c, "eg": f"{count} 张"}
            icon_img = load_icon_image(f"{c}.png")
            if icon_img is not None:
                item["icon"] = icon_img
            data.append(item)
        help_text = f"共 {len(char_names)} 个角色"
    else:
        total = sum(len(pics) for pics in chars.values())
        data = [{"name": "（散图）", "eg": f"{total} 张未分类"}]
        help_text = f"{total} 张散图"

    entry = {
        "name": artist,
        "help": help_text,
        "desc": "",
        "color": COLORS[0],
        "data": data,
    }
    if cat_icon is not None:
        entry["icon"] = cat_icon
    plugin_help = {artist: entry}

    result = await get_new_help(
        plugin_name=f"画师「{artist}」· 角色一览",
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