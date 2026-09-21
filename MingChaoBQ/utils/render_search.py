"""搜索表情结果列表图：淡蓝色卡片列表，背景沿用「bq帮助」的背景图。"""

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread

from .cache import clean_cache, new_cache_path
from .help_assets import load_bg, get_max_width
from .image_utils import FontType, fit_text, get_font
from .index_types import PicEntry

# 淡蓝主基调
ACCENT = (74, 144, 217)  # #4A90D9
ACCENT_SOFT = (158, 200, 238)
TITLE_FILL = (24, 68, 118)
TEXT_FILL = (38, 64, 92)
META_FILL = (118, 148, 178)
CARD_FILL_A = (255, 255, 255, 178)
CARD_FILL_B = (237, 246, 255, 178)
# 淡蓝白纱：压住背景图，保证文字可读，同时整体偏淡蓝
VEIL_FILL = (244, 250, 255, 216)

CANVAS_WIDTH = 980
PADDING = 28
HEADER_HEIGHT = 96
ROW_HEIGHT = 46
ROW_GAP = 10
# 匹配可能上百条，超过这个数量只画前面这些，避免图过长
MAX_ITEMS = 300


def _cover(img: Image.Image, width: int, height: int) -> Image.Image:
    """等比缩放后居中裁剪，铺满目标尺寸。"""
    scale = max(width / img.width, height / img.height)
    resized = img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _base_canvas(width: int, height: int) -> Image.Image:
    """帮助图同款背景 + 淡蓝纱 + 自上而下的淡蓝渐变；没配背景时用淡蓝底兜底。"""
    bg = load_bg("mcbq_help_bg")
    if bg is None:
        canvas = Image.new("RGBA", (width, height), (232, 243, 253, 255))
    else:
        canvas = _cover(bg.convert("RGBA"), width, height)
        canvas = Image.alpha_composite(canvas, Image.new("RGBA", (width, height), VEIL_FILL))

    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for y in range(height):
        alpha = round(66 * (1 - y / height))
        gradient_draw.line([(0, y), (width, y)], fill=(*ACCENT, alpha))
    return Image.alpha_composite(canvas, gradient)


def _draw_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    center_y: int,
    text: str,
    font: FontType,
    fill: tuple[int, int, int],
    right: int | None = None,
) -> None:
    """按视觉中线对齐绘制文字；给 right 时右对齐。不用 anchor，兼容位图兜底字体。"""
    bbox = font.getbbox(text)
    y = center_y - (bbox[1] + bbox[3]) // 2
    if right is not None:
        x = right - round(font.getlength(text))
    draw.text((x, y), text, font=font, fill=fill)


def _row_meta(pic: PicEntry) -> str:
    artist = pic.get("_artist", "")
    char = pic.get("_char", "")
    if pic.get("source") == "api" or artist == "API":
        return f"API · {char}"
    return f"{artist} · {char}"


@to_thread
def render_emotion_list(items: list[PicEntry], keyword: str, fuzzy: bool = False) -> Path:
    """把搜索结果渲染成列表图并返回缓存路径，可直接传给 MessageSegment.image()。"""
    shown = items[:MAX_ITEMS]
    columns = 1 if len(shown) <= 12 else 2
    rows = max(1, -(-len(shown) // columns))

    width = CANVAS_WIDTH
    height = PADDING * 2 + HEADER_HEIGHT + 18 + rows * ROW_HEIGHT + (rows - 1) * ROW_GAP
    canvas = _base_canvas(width, height)

    # 半透明卡片/文字先画在透明层上再合成，避免直接落盘时 alpha 变成"镂空"
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    title_font = get_font(36)
    sub_font = get_font(20)
    name_font = get_font(24)
    meta_font = get_font(19)
    index_font = get_font(17)

    draw.rounded_rectangle(
        (PADDING, PADDING, width - PADDING, PADDING + HEADER_HEIGHT),
        radius=18,
        fill=(255, 255, 255, 198),
        outline=(*ACCENT_SOFT, 255),
        width=2,
    )
    draw.rounded_rectangle(
        (PADDING, PADDING + 18, PADDING + 8, PADDING + HEADER_HEIGHT - 18),
        radius=4,
        fill=(*ACCENT, 255),
    )
    _draw_text(
        draw,
        PADDING + 30,
        PADDING + 40,
        fit_text(f"搜索「{keyword}」", title_font, width - 2 * PADDING - 60),
        title_font,
        TITLE_FILL,
    )

    subtitle = f"共 {len(items)} 个" + ("（模糊匹配）" if fuzzy else "")
    if len(items) > MAX_ITEMS:
        subtitle += f" · 仅显示前 {MAX_ITEMS} 个"
    _draw_text(draw, PADDING + 32, PADDING + 72, subtitle, sub_font, META_FILL)

    column_width = (width - PADDING * 2 - (columns - 1) * ROW_GAP) // columns
    # 左侧序号占 54px, 右侧内边距 14px; 表情名短、画师/角色名长, 按 35% : 65% 分
    available = column_width - 54 - 14
    name_width = round(available * 0.35)
    meta_width = available - name_width - 16
    top = PADDING + HEADER_HEIGHT + 18

    for index, pic in enumerate(shown):
        column, row = divmod(index, rows)
        x0 = PADDING + column * (column_width + ROW_GAP)
        y0 = top + row * (ROW_HEIGHT + ROW_GAP)
        draw.rounded_rectangle(
            (x0, y0, x0 + column_width, y0 + ROW_HEIGHT),
            radius=12,
            fill=CARD_FILL_A if row % 2 == 0 else CARD_FILL_B,
            outline=(*ACCENT_SOFT, 170),
            width=1,
        )
        center_y = y0 + ROW_HEIGHT // 2
        _draw_text(draw, x0 + 16, center_y, str(index + 1), index_font, ACCENT)
        _draw_text(
            draw,
            x0 + 54,
            center_y,
            fit_text(pic["emotion"], name_font, name_width),
            name_font,
            TEXT_FILL,
        )
        _draw_text(
            draw,
            x0,
            center_y,
            fit_text(_row_meta(pic), meta_font, meta_width),
            meta_font,
            META_FILL,
            right=x0 + column_width - 14,
        )

    canvas = Image.alpha_composite(canvas, layer).convert("RGB")

    max_width = get_max_width()
    if canvas.width > max_width:
        ratio = max_width / canvas.width
        canvas = canvas.resize((max_width, round(canvas.height * ratio)), Image.LANCZOS)

    clean_cache()
    path = new_cache_path("search", ".jpg")
    # subsampling=0(4:4:4) 保住小字号文字边缘，质量 88 体积可控
    canvas.save(path, format="JPEG", quality=88, subsampling=0, optimize=True)
    return path
