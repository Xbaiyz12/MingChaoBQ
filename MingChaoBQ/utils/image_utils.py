"""把长文本渲染成 PNG（搜索表情的结果列表用）。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gsuid_core.pool import to_thread

from .cache import clean_cache, new_cache_path

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


def _get_font(size: int) -> FontType:
    """按优先级查找可用的中文字体，全都没有时退回 Pillow 内置位图字体。"""
    for path in _FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap_line(line: str, font: FontType, max_px: int) -> list[str]:
    """把一行超长文本按像素宽度折成多行"""
    if not line:
        return [""]
    result: list[str] = []
    current = ""
    for ch in line:
        test = current + ch
        if font.getlength(test) > max_px and current:
            result.append(current)
            current = ch
        else:
            current = test
    if current:
        result.append(current)
    return result


@to_thread
def render_text_to_image(
    text: str,
    title: str = "",
    width: int = 900,
    font_size: int = 22,
    title_size: int = 28,
    line_height: int = 36,
    padding: int = 30,
    bg_color: tuple[int, int, int] = (255, 255, 255),
    text_color: tuple[int, int, int] = (30, 30, 30),
    title_color: tuple[int, int, int] = (60, 110, 180),
) -> Path:
    """
    把长文本渲染成 PNG 图片，保存到缓存目录并返回文件路径，可直接传给 MessageSegment.image()。
    """
    font = _get_font(font_size)
    title_font = _get_font(title_size)
    max_text_width = width - 2 * padding

    wrapped_lines: list[str] = []
    for line in text.split("\n"):
        wrapped_lines.extend(_wrap_line(line, font, max_text_width))

    height = padding
    if title:
        height += title_size + 20
    height += line_height * len(wrapped_lines) + padding

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    y = padding
    if title:
        draw.text((padding, y), title, font=title_font, fill=title_color)
        y += title_size + 20

    for line in wrapped_lines:
        draw.text((padding, y), line, font=font, fill=text_color)
        y += line_height

    clean_cache()
    filepath = new_cache_path("text")
    img.save(filepath, format="PNG")
    return filepath
