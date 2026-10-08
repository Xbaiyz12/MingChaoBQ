"""表情候选列表图：缩略图网格，让用户看清是哪个表情后按编号选。"""

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread

from .cache import clean_cache, new_cache_path
from .paths import BQ_ROOT
from .help_assets import load_bg, get_max_width
from .image_utils import FontType, fit_text, get_font, load_thumb_frame
from .index_types import PicEntry

# 淡蓝主基调
ACCENT = (74, 144, 217)  # #4A90D9
ACCENT_SOFT = (158, 200, 238)
TITLE_FILL = (24, 68, 118)
TEXT_FILL = (38, 64, 92)
META_FILL = (118, 148, 178)
CARD_FILL = (255, 255, 255, 198)
# 淡蓝白纱：压住背景图，保证文字可读，同时整体偏淡蓝
VEIL_FILL = (244, 250, 255, 216)

CANVAS_WIDTH = 980
PADDING = 28
HEADER_HEIGHT = 96
GRID_COLS = 5
THUMB_BOX = 150
# 缩略图 150 + 编号 + 表情名 + 画师·角色 三行文字的总高
CARD_HEIGHT = 240
CARD_GAP = 10
# 每个候选都要解码缩略图；50 张是「够挑」与「图不至于太长」之间的折中
MAX_LIST_ITEMS = 50


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
    center: int | None = None,
) -> None:
    """按视觉中线对齐绘制文字；给 right 右对齐、给 center 居中。

    不用 anchor，兼容位图兜底字体。
    """
    bbox = font.getbbox(text)
    y = center_y - (bbox[1] + bbox[3]) // 2
    if center is not None:
        x = center - round(font.getlength(text) / 2)
    elif right is not None:
        x = right - round(font.getlength(text))
    draw.text((x, y), text, font=font, fill=fill)


def _paste_thumb(canvas: Image.Image, thumb: Image.Image, x0: int, y0: int, card_width: int, box: int) -> None:
    """把已等比缩放的缩略图居中贴到卡片上部。"""
    canvas.paste(thumb, (x0 + (card_width - thumb.width) // 2, y0 + (box - thumb.height) // 2))


def _row_meta(pic: PicEntry) -> str:
    artist = pic.get("_artist", "")
    char = pic.get("_char", "")
    if pic.get("source") == "api" or artist == "API":
        return f"API · {char}"
    return f"{artist} · {char}"


@to_thread
def render_emotion_list(
    items: list[PicEntry],
    keyword: str,
    note: str = "",
    hint: str = "",
    total: int | None = None,
) -> Path:
    """把表情候选渲染成缩略图网格，编号（表情1、表情2…）可直接被用户回复引用。

    items 是实际要画的候选（调用方可能已按角色抽样），total 是命中总数，
    用于副标题的「共 N 个」与底部的「另有 M 个未显示」。
    缩略图取「有内容的那一帧」：很多表情动图开头是空白帧，用第 0 帧会让
    整屏缩略图都是白的，用户没法分辨。
    """
    shown = items[:MAX_LIST_ITEMS]
    total_count = len(items) if total is None else total
    rows = max(1, -(-len(shown) // GRID_COLS))
    hidden = total_count - len(shown)

    width = CANVAS_WIDTH
    height = PADDING * 2 + HEADER_HEIGHT + 18 + rows * CARD_HEIGHT + (rows - 1) * CARD_GAP
    if hidden > 0:
        height += 34
    canvas = _base_canvas(width, height)

    title_font = get_font(36)
    sub_font = get_font(19)
    index_font = get_font(21)
    name_font = get_font(19)
    meta_font = get_font(16)

    header = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    head_draw = ImageDraw.Draw(header)
    head_draw.rounded_rectangle(
        (PADDING, PADDING, width - PADDING, PADDING + HEADER_HEIGHT),
        radius=18,
        fill=CARD_FILL,
        outline=(*ACCENT_SOFT, 255),
        width=2,
    )
    head_draw.rounded_rectangle(
        (PADDING, PADDING + 18, PADDING + 8, PADDING + HEADER_HEIGHT - 18),
        radius=4,
        fill=(*ACCENT, 255),
    )
    _draw_text(
        head_draw,
        PADDING + 30,
        PADDING + 38,
        fit_text(f"表情「{keyword}」", title_font, width - 2 * PADDING - 60),
        title_font,
        TITLE_FILL,
    )
    parts = [f"共 {total_count} 个"]
    if note:
        parts.append(note)
    if hint:
        parts.append(hint)
    _draw_text(head_draw, PADDING + 32, PADDING + 72, " · ".join(parts), sub_font, META_FILL)
    canvas = Image.alpha_composite(canvas, header)

    body = ImageDraw.Draw(canvas)
    card_width = (width - PADDING * 2 - (GRID_COLS - 1) * CARD_GAP) // GRID_COLS
    top = PADDING + HEADER_HEIGHT + 18

    for slot, pic in enumerate(shown):
        row, column = divmod(slot, GRID_COLS)
        x0 = PADDING + column * (card_width + CARD_GAP)
        y0 = top + row * (CARD_HEIGHT + CARD_GAP)
        body.rounded_rectangle(
            (x0, y0, x0 + card_width, y0 + CARD_HEIGHT),
            radius=12,
            fill=(255, 255, 255),
            outline=(*ACCENT_SOFT, 255),
            width=2,
        )
        thumb = load_thumb_frame(BQ_ROOT / pic["file"], THUMB_BOX)
        if thumb is None:
            body.rectangle((x0 + 8, y0 + 8, x0 + card_width - 8, y0 + 8 + THUMB_BOX), fill=(226, 236, 246))
        else:
            _paste_thumb(canvas, thumb, x0, y0, card_width, THUMB_BOX)
        _draw_text(
            body,
            x0,
            y0 + THUMB_BOX + 24,
            f"表情{slot + 1}",
            index_font,
            ACCENT,
            center=x0 + card_width // 2,
        )
        _draw_text(
            body,
            x0,
            y0 + THUMB_BOX + 50,
            fit_text(pic["emotion"], name_font, card_width - 15),
            name_font,
            TEXT_FILL,
            center=x0 + card_width // 2,
        )
        _draw_text(
            body,
            x0,
            y0 + THUMB_BOX + 74,
            fit_text(_row_meta(pic), meta_font, card_width - 15),
            meta_font,
            META_FILL,
            center=x0 + card_width // 2,
        )

    if hidden > 0:
        _draw_text(
            body,
            PADDING + 4,
            top + rows * (CARD_HEIGHT + CARD_GAP) + 6,
            f"另有 {hidden} 个未显示，请用更精确的关键词缩小范围",
            sub_font,
            META_FILL,
        )

    max_width = get_max_width()
    if canvas.width > max_width:
        ratio = max_width / canvas.width
        canvas = canvas.resize((max_width, round(canvas.height * ratio)), Image.LANCZOS)

    clean_cache()
    path = new_cache_path("emotion-list", ".jpg")
    # subsampling=0(4:4:4) 保住小字号文字边缘，质量 88 体积可控
    canvas.convert("RGB").save(path, format="JPEG", quality=88, subsampling=0, optimize=True)
    return path
