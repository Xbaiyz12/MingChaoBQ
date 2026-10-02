"""MingChaoBQ 重复表情报告图渲染。"""

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread

from .cache import clean_cache, new_cache_path
from .paths import BQ_ROOT
from ..dedupe import DupGroup, DupReport, read_content_frame
from .help_assets import build_canvas
from .image_utils import fit_text, get_font

_WIDTH = 980
_PADDING = 32
_MAX_GROUPS = 10
_MAX_PER_GROUP = 12
_CARD_W = 150
_THUMB_H = 112
_THUMB_W = 138
_COLS = 6
_HEADER_H = 82
_GROUP_HEAD_H = 38
_ROW_H = _THUMB_H + 46
_ACCENT = (74, 144, 217)
_TEXT = (38, 64, 92)
_MUTED = (118, 148, 178)
_DANGER = (198, 92, 92)


def _short(file: str) -> str:
    """只保留路径末两段，报告里够定位又不至于刷屏。"""
    parts = file.split("/")
    return "/".join(parts[-2:]) if len(parts) > 2 else file


def _load_thumb(file: str) -> Image.Image | None:
    read = read_content_frame(BQ_ROOT / file)
    if read is None:
        return None
    image, _ = read
    image = image.convert("RGB")
    scale = min(_THUMB_W / image.width, _THUMB_H / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def _human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def _group_height(group: DupGroup) -> int:
    shown = min(len(group["items"]), _MAX_PER_GROUP)
    rows = max(1, (shown + _COLS - 1) // _COLS)
    return _GROUP_HEAD_H + rows * _ROW_H + 14


@to_thread
def _render(report: DupReport) -> Path:
    shown_groups = report["groups"][:_MAX_GROUPS]
    height = _PADDING * 2 + _HEADER_H + 20
    for group in shown_groups:
        height += _group_height(group)
    if len(report["groups"]) > len(shown_groups):
        height += 34

    image = build_canvas(_WIDTH, height)
    draw = ImageDraw.Draw(image)
    title_font = get_font(36)
    sub_font = get_font(18)
    name_font = get_font(19)
    meta_font = get_font(17)
    num_font = get_font(20)

    draw.rounded_rectangle(
        (_PADDING, _PADDING, _WIDTH - _PADDING, _PADDING + _HEADER_H),
        radius=18,
        fill=(255, 255, 255),
        outline=_ACCENT,
        width=2,
    )
    draw.text((_PADDING + 24, _PADDING + 18), "表情包查重", font=title_font, fill=_TEXT)
    draw.text(
        (_PADDING + 26, _PADDING + 58),
        f"扫描 {report['scanned']} 张 · 发现 {len(report['groups'])} 组重复 · "
        f"涉及 {report['total_items']} 张 · 可省约 {_human(report['waste_size'])}",
        font=sub_font,
        fill=_MUTED,
    )

    top = _PADDING + _HEADER_H + 20
    for index, group in enumerate(shown_groups, 1):
        block_h = _group_height(group)
        draw.rounded_rectangle(
            (_PADDING, top, _WIDTH - _PADDING, top + block_h - 10),
            radius=14,
            fill=(255, 255, 255),
            outline=(158, 200, 238),
        )
        draw.text((_PADDING + 16, top + 10), f"第 {index} 组", font=num_font, fill=_ACCENT)
        draw.text(
            (_PADDING + 106, top + 12),
            f"{len(group['items'])} 张 · 可省 {_human(group['dup_size'])} · 建议保留 {_short(group['keep'])}",
            font=meta_font,
            fill=_MUTED,
        )

        items = group["items"][:_MAX_PER_GROUP]
        for slot, item in enumerate(items):
            row, col = divmod(slot, _COLS)
            x = _PADDING + 16 + col * _CARD_W
            y = top + _GROUP_HEAD_H + row * _ROW_H
            thumb = _load_thumb(item["file"])
            if thumb is None:
                draw.rectangle((x, y, x + _THUMB_W, y + _THUMB_H), fill=(225, 235, 245))
            else:
                image.paste(thumb, (x + (_THUMB_W - thumb.width) // 2, y + (_THUMB_H - thumb.height) // 2))
            label = _short(item["file"]).split("/")[-1]
            draw.text((x, y + _THUMB_H + 4), fit_text(label, name_font, _THUMB_W), font=name_font, fill=_TEXT)
            draw.text((x, y + _THUMB_H + 26), _human(item["size"]), font=meta_font, fill=_MUTED)
            if item["file"] == group["keep"]:
                draw.rectangle((x, y, x + _THUMB_W, y + _THUMB_H), outline=(120, 190, 130), width=3)

        if len(group["items"]) > _MAX_PER_GROUP:
            extra_row = (len(items) + _COLS - 1) // _COLS
            draw.text(
                (_PADDING + 16, top + _GROUP_HEAD_H + extra_row * _ROW_H - 14),
                f"…另有 {len(group['items']) - _MAX_PER_GROUP} 张同类重复未展示",
                font=meta_font,
                fill=_DANGER,
            )
        top += block_h

    if len(report["groups"]) > len(shown_groups):
        draw.text(
            (_PADDING + 6, top + 4),
            f"还有 {len(report['groups']) - len(shown_groups)} 组未展示，建议先清理上面这些",
            font=meta_font,
            fill=_DANGER,
        )

    clean_cache()
    path = new_cache_path("dedupe", ".jpg")
    image.save(path, format="JPEG", quality=88, optimize=True)
    return path


async def render_dedupe_report(report: DupReport) -> Path:
    """把重复分组渲染成报告图。"""
    return await _render(report)
