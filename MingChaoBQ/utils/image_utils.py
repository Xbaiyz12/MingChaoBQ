"""渲染共用工具：中文字体查找 + 文本测量/截断。"""

from pathlib import Path

from PIL import ImageFont

FontType = ImageFont.FreeTypeFont | ImageFont.ImageFont

_FONT_CANDIDATES = (
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
            return ImageFont.truetype(str(path), size)
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
