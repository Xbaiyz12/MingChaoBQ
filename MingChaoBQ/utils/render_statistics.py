"""MingChaoBQ 统计图渲染。"""

import asyncio
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread
from gsuid_core.utils.image.image_tools import get_qq_avatar

from .cache import clean_cache, new_cache_path
from ..statistics import StatsData
from .help_assets import load_bg
from .image_utils import fit_text, get_font

_WIDTH = 980
_PADDING = 32
_ROW_HEIGHT = 76
_MAX_ROWS = 30
_AVATAR_SIZE = 52
_ACCENT = (74, 144, 217)
_TEXT = (38, 64, 92)
_MUTED = (118, 148, 178)


def _base(height: int) -> Image.Image:
    bg = load_bg("mcbq_help_bg")
    if bg is None:
        return Image.new("RGB", (_WIDTH, height), (232, 243, 253))
    image = bg.convert("RGB")
    scale = max(_WIDTH / image.width, height / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left = (image.width - _WIDTH) // 2
    top = (image.height - height) // 2
    image = image.crop((left, top, left + _WIDTH, top + height))
    veil = Image.new("RGBA", image.size, (244, 250, 255, 220))
    return Image.alpha_composite(image.convert("RGBA"), veil).convert("RGB")


def _sorted_rows(rows: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """次数降序、同次数按名称升序。"""
    return sorted(rows, key=lambda item: (-item[1], item[0]))


def _circle_avatar(image: Image.Image, size: int) -> Image.Image:
    """裁成圆形头像，方形原图直接贴上去在圆角卡片里很突兀。"""
    avatar = image.convert("RGBA").resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    avatar.putalpha(mask)
    return avatar


@to_thread
def _render(
    title: str,
    rows: list[tuple[str, int]],
    prefix: str,
    labels: dict[str, tuple[str, str]] | None = None,
    avatars: dict[str, Image.Image] | None = None,
) -> Path:
    shown = _sorted_rows(rows)[:_MAX_ROWS]
    height = _PADDING * 2 + 100 + len(shown) * _ROW_HEIGHT
    image = _base(height)
    draw = ImageDraw.Draw(image)
    title_font = get_font(36)
    name_font = get_font(24)
    count_font = get_font(24)
    muted_font = get_font(18)
    draw.rounded_rectangle(
        (_PADDING, _PADDING, _WIDTH - _PADDING, _PADDING + 82),
        radius=18,
        fill=(255, 255, 255),
        outline=_ACCENT,
        width=2,
    )
    draw.text((_PADDING + 24, _PADDING + 20), title, font=title_font, fill=_TEXT)
    total = sum(value for _, value in rows)
    draw.text(
        (_PADDING + 26, _PADDING + 62),
        f"共 {total} 次 · 显示前 {len(shown)} 项" if shown else f"共 {total} 次 · 暂无记录",
        font=muted_font,
        fill=_MUTED,
    )
    top = _PADDING + 100
    for index, (name, count) in enumerate(shown):
        y = top + index * _ROW_HEIGHT
        fill = (255, 255, 255) if index % 2 == 0 else (237, 246, 255)
        draw.rounded_rectangle(
            (_PADDING, y, _WIDTH - _PADDING, y + _ROW_HEIGHT - 8),
            radius=12,
            fill=fill,
            outline=(158, 200, 238),
        )
        draw.text((_PADDING + 18, y + 18), f"{index + 1}", font=muted_font, fill=_ACCENT)
        text_x = _PADDING + 70
        if avatars is not None and name in avatars:
            avatar = _circle_avatar(avatars[name], _AVATAR_SIZE)
            image.paste(avatar, (_PADDING + 58, y + 6), avatar)
            text_x = _PADDING + 126
        label = labels[name] if labels is not None and name in labels else (name, "")
        sub = "" if label[1] == label[0] else label[1]
        main_y = y + 4 if sub else y + 18
        draw.text((text_x, main_y), fit_text(label[0], name_font, _WIDTH - 340), font=name_font, fill=_TEXT)
        if sub:
            draw.text((text_x, y + 38), fit_text(sub, muted_font, _WIDTH - 340), font=muted_font, fill=_MUTED)
        count_text = f"{count} 次"
        count_width = round(count_font.getlength(count_text))
        draw.text(
            (_WIDTH - _PADDING - 20 - count_width, y + 18),
            count_text,
            font=count_font,
            fill=_ACCENT,
        )
    clean_cache()
    path = new_cache_path(prefix, ".jpg")
    image.save(path, format="JPEG", quality=88, optimize=True)
    return path


async def _load_avatars(users: dict[str, str]) -> dict[str, Image.Image]:
    """有平台下发的头像 URL 就用它，否则按 QQ 号取 qlogo。"""
    if not users:
        return {}
    tasks = [get_qq_avatar(None, url) if url else get_qq_avatar(key) for key, url in users.items()]
    results = await asyncio.gather(*tasks)
    return {key: image for key, image in zip(users, results, strict=True) if image is not None}


async def render_poke_statistics(data: StatsData) -> Path:
    """渲染被戳总次数与用户排行（头像 + 昵称，昵称下方为 QQ 号）。"""
    rows = [(key, value["count"]) for key, value in data["poke_users"].items()]
    labels = {key: (value["name"], key) for key, value in data["poke_users"].items()}
    top_keys = [key for key, _ in _sorted_rows(rows)[:_MAX_ROWS]]
    avatars = await _load_avatars({key: data["poke_users"][key]["avatar"] for key in top_keys})
    return await _render("戳一戳统计", rows, "poke-stats", labels, avatars)


async def render_role_statistics(data: StatsData) -> Path:
    """渲染角色名发送排行。"""
    return await _render("角色表情发送统计", list(data["roles"].items()), "role-stats")
