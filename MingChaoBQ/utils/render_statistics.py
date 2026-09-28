"""MingChaoBQ 统计图渲染。"""

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread

from .cache import clean_cache, new_cache_path
from ..statistics import _StatsData
from .help_assets import load_bg
from .image_utils import fit_text, get_font

_WIDTH = 980
_PADDING = 32
_ROW_HEIGHT = 52
_MAX_ROWS = 30
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


@to_thread
def _render(title: str, rows: list[tuple[str, int]], prefix: str) -> Path:
    shown = sorted(rows, key=lambda item: (-item[1], item[0]))[:_MAX_ROWS]
    height = _PADDING * 2 + 100 + max(1, len(shown)) * _ROW_HEIGHT
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
    draw.text(
        (_PADDING + 26, _PADDING + 62),
        f"共 {sum(value for _, value in rows)} 次 · 显示前 {len(shown)} 项",
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
        draw.text((_PADDING + 18, y + 11), f"{index + 1}", font=muted_font, fill=_ACCENT)
        draw.text(
            (_PADDING + 70, y + 8),
            fit_text(name, name_font, _WIDTH - 280),
            font=name_font,
            fill=_TEXT,
        )
        count_text = f"{count} 次"
        count_width = round(count_font.getlength(count_text))
        draw.text(
            (_WIDTH - _PADDING - 20 - count_width, y + 8),
            count_text,
            font=count_font,
            fill=_ACCENT,
        )
    clean_cache()
    path = new_cache_path(prefix, ".jpg")
    image.save(path, format="JPEG", quality=88, optimize=True)
    return path


async def render_poke_statistics(data: _StatsData) -> Path:
    """渲染戳一戳用户统计图。"""
    return await _render("戳一戳统计", list(data["poke_users"].items()), "poke-stats")


async def render_emotion_statistics(data: _StatsData) -> Path:
    """渲染表情名发送统计图。"""
    return await _render("表情发送统计", list(data["emotions"].items()), "emotion-stats")
