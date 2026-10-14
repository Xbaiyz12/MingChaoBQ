"""通用榜单渲染：单列竖排、序号自上而下，统计图与小站列表图共用。"""

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread

from .cache import clean_cache, new_cache_path
from .help_assets import build_canvas
from .image_utils import fit_text, get_font

WIDTH = 980
PADDING = 32
ROW_HEIGHT = 76
MAX_ROWS = 30
AVATAR_SIZE = 52
ACCENT = (74, 144, 217)
TEXT = (38, 64, 92)
MUTED = (118, 148, 178)
# 名字在 dim 里的行用这套颜色，表示「本地还没有、建议拉取」
DIM_TEXT = (172, 188, 204)
DIM_ACCENT = (190, 205, 218)
DIM_FILL = (249, 252, 254)


def sorted_rows(rows: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """数量降序、同数量按名称升序。"""
    return sorted(rows, key=lambda item: (-item[1], item[0]))


def circle_avatar(image: Image.Image, size: int) -> Image.Image:
    """裁成圆形头像，方形原图直接贴上去在圆角卡片里很突兀。"""
    avatar = image.convert("RGBA").resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    avatar.putalpha(mask)
    return avatar


@to_thread
def render_rank(
    title: str,
    rows: list[tuple[str, int]],
    prefix: str,
    unit: str = "次",
    labels: dict[str, tuple[str, str]] | None = None,
    avatars: dict[str, Image.Image] | None = None,
    dim: set[str] | None = None,
    summary_extra: str = "",
) -> Path:
    """渲染一张榜单图。labels 给某行加主/副标题，avatars 有则显示圆形头像。

    dim 里的名字整行画成浅色（用于「本地还没有、需要拉取」这类对比）。
    """
    shown = sorted_rows(rows)[:MAX_ROWS]
    height = PADDING * 2 + 100 + len(shown) * ROW_HEIGHT
    image = build_canvas(WIDTH, height)
    draw = ImageDraw.Draw(image)
    title_font = get_font(36)
    name_font = get_font(24)
    count_font = get_font(24)
    muted_font = get_font(18)
    draw.rounded_rectangle(
        (PADDING, PADDING, WIDTH - PADDING, PADDING + 82),
        radius=18,
        fill=(255, 255, 255),
        outline=ACCENT,
        width=2,
    )
    draw.text((PADDING + 24, PADDING + 20), title, font=title_font, fill=TEXT)
    total = sum(value for _, value in rows)
    summary = f"共 {total} {unit} · 显示前 {len(shown)} 项" if shown else "暂无数据"
    if summary_extra:
        summary = f"{summary} · {summary_extra}"
    draw.text((PADDING + 26, PADDING + 62), summary, font=muted_font, fill=MUTED)
    top = PADDING + 100
    for index, (name, count) in enumerate(shown):
        y = top + index * ROW_HEIGHT
        is_dim = dim is not None and name in dim
        text_color = DIM_TEXT if is_dim else TEXT
        accent_color = DIM_ACCENT if is_dim else ACCENT
        fill = DIM_FILL if is_dim else ((255, 255, 255) if index % 2 == 0 else (237, 246, 255))
        draw.rounded_rectangle(
            (PADDING, y, WIDTH - PADDING, y + ROW_HEIGHT - 8),
            radius=12,
            fill=fill,
            outline=(198, 216, 232) if is_dim else (158, 200, 238),
        )
        draw.text((PADDING + 18, y + 18), f"{index + 1}", font=muted_font, fill=accent_color)
        text_x = PADDING + 70
        if avatars is not None and name in avatars:
            avatar = circle_avatar(avatars[name], AVATAR_SIZE)
            image.paste(avatar, (PADDING + 58, y + 6), avatar)
            text_x = PADDING + 126
        label = labels[name] if labels is not None and name in labels else (name, "")
        sub = "" if label[1] == label[0] else label[1]
        main_y = y + 4 if sub else y + 18
        draw.text((text_x, main_y), fit_text(label[0], name_font, WIDTH - 340), font=name_font, fill=text_color)
        if sub:
            draw.text(
                (text_x, y + 38),
                fit_text(sub, muted_font, WIDTH - 340),
                font=muted_font,
                fill=DIM_TEXT if is_dim else MUTED,
            )
        count_text = f"{count} {unit}"
        count_width = round(count_font.getlength(count_text))
        draw.text((WIDTH - PADDING - 20 - count_width, y + 18), count_text, font=count_font, fill=accent_color)
    clean_cache()
    path = new_cache_path(prefix, ".jpg")
    image.save(path, format="JPEG", quality=88, optimize=True)
    return path
