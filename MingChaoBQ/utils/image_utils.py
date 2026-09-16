import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .paths import BQ_ROOT

# 缓存目录：data/MingChaoBQ/cache/
CACHE_DIR = BQ_ROOT / "cache"


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """按优先级查找可用的中文字体"""
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),      # 微软雅黑
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),    # 黑体
        Path("C:/Windows/Fonts/simsun.ttc"),    # 宋体
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _wrap_line(line: str, font: ImageFont.FreeTypeFont, max_px: int) -> list:
    """把一行超长文本按像素宽度折成多行"""
    if not line:
        return [""]
    result = []
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


def _clean_cache():
    """清理缓存目录中超过 1 小时的旧文件"""
    try:
        if not CACHE_DIR.exists():
            return
        now = time.time()
        for f in CACHE_DIR.iterdir():
            if f.is_file() and now - f.stat().st_mtime > 3600:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def render_text_to_image(
    text: str,
    title: str = "",
    width: int = 900,
    font_size: int = 22,
    title_size: int = 28,
    line_height: int = 36,
    padding: int = 30,
    bg_color: tuple = (255, 255, 255),
    text_color: tuple = (30, 30, 30),
    title_color: tuple = (60, 110, 180),
) -> Path:
    """
    把长文本渲染成 PNG 图片，保存到缓存目录，返回文件路径。
    可直接传给 MessageSegment.image()。
    """
    font = _get_font(font_size)
    title_font = _get_font(title_size)

    max_text_width = width - 2 * padding

    # 折行处理
    wrapped_lines = []
    for line in text.split("\n"):
        wrapped_lines.extend(_wrap_line(line, font, max_text_width))

    # 计算图片高度
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

    # 保存到缓存
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _clean_cache()
    filepath = CACHE_DIR / f"text_{int(time.time() * 1000)}.png"
    img.save(filepath, format="PNG")
    return filepath