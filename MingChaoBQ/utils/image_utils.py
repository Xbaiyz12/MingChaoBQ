"""渲染共用工具：中文字体查找 + 文本测量/截断 + 表情缩略图。"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageFont, ImageSequence

from gsuid_core.utils.fonts.fonts import FONT_ORIGIN_PATH

FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont

# 缩略图最多往后找多少帧；表情动图开头常是淡入空白帧
_THUMB_SCAN_FRAMES = 12
# 边缘能量达到这个值就算有内容，不用继续找
_THUMB_ENOUGH = 8.0

_FONT_CANDIDATES = (
    FONT_ORIGIN_PATH,  # 优先复用 GsCore 官方自带 MiSansVF
    Path("C:/Windows/Fonts/msyh.ttc"),  # 微软雅黑
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),  # 黑体
    Path("C:/Windows/Fonts/simsun.ttc"),  # 宋体
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
)


def get_font(size: int) -> FontType:
    """按优先级查找可用的中文字体，全都没有时退回 Pillow 内置位图字体。"""
    for path in _FONT_CANDIDATES:
        if path.exists():
            font = ImageFont.truetype(str(path), size)
            set_axes = getattr(font, "set_variation_by_axes", None)
            if callable(set_axes):
                try:
                    set_axes([630.0])
                except (OSError, ValueError, TypeError):
                    pass
            return font
    return ImageFont.load_default()


def fit_text(text: str, font: FontType, max_px: int) -> str:
    """文字超宽时按像素宽度截断并加省略号，避免和右侧内容重叠。"""
    if max_px <= 0 or font.getlength(text) <= max_px:
        return text
    ellipsis = "…"
    ellipsis_width = font.getlength(ellipsis)
    if ellipsis_width > max_px:
        return ""
    kept = ""
    for char in text:
        if font.getlength(kept + char) + ellipsis_width > max_px:
            break
        kept += char
    return kept + ellipsis


def _flatten(image: Image.Image) -> Image.Image:
    """透明底铺白，避免透明像素在缩略图里显示成黑块。"""
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")
    return image.convert("RGB")


def _content_score(image: Image.Image) -> float:
    """内容复杂度 = 相邻像素差分均值。纯色帧（含全黑帧）接近 0。"""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    if gray.shape[0] < 2 or gray.shape[1] < 2:
        return 0.0
    return float(np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean())


def load_thumb_frame(path: Path, size: int) -> Image.Image | None:
    """取一张能代表该表情的缩略图。

    不能直接用第 0 帧：很多表情动图开头是淡入空白帧（实测帧 0 内容为 0，
    真正的画面在第 19 帧附近），那样列表里会出现一片空白缩略图。
    帧数走 ImageSequence：n_frames 只在多帧格式类上存在，JPEG 上会抛错。
    """
    try:
        with Image.open(path) as image:
            total = sum(1 for _ in ImageSequence.Iterator(image))
            if total <= 1:
                image.seek(0)
                thumb = _flatten(image)
            else:
                best: Image.Image | None = None
                best_score = -1.0
                step = max(1, total // _THUMB_SCAN_FRAMES)
                for index in range(0, total, step):
                    image.seek(index)
                    candidate = _flatten(image)
                    score = _content_score(candidate)
                    if score > best_score:
                        best, best_score = candidate, score
                    if best_score >= _THUMB_ENOUGH:
                        break
                if best is None:
                    return None
                thumb = best
    except (OSError, ValueError):
        return None

    scale = min(size / thumb.width, size / thumb.height)
    resized = thumb.resize(
        (max(1, round(thumb.width * scale)), max(1, round(thumb.height * scale))),
        Image.LANCZOS,
    )
    return resized
