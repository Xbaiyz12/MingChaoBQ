"""帮助图 / 一览图的素材查找与结果压缩。"""

from io import BytesIO
from pathlib import Path

from PIL import Image

from gsuid_core.logger import logger

from .cache import clean_cache, new_cache_path
from .paths import BQ_ROOT
from ..mingchao_config import StrKey, get_int, get_str

# 插件根目录：plugins/MingChaoBQ/
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# 插件自带的默认图标目录（随 GitHub 仓库走）
PLUGIN_ICON_DIR = PLUGIN_ROOT / "MingChaoBQ" / "icons"

# 用户自定义图标目录（可选覆盖）
DATA_ICON_DIR = BQ_ROOT / "icons"

# 插件主图标（帮助图顶部那个）
PLUGIN_ICON = PLUGIN_ROOT / "ICON.png"

# 框架 get_new_help 未标注返回类型，实际是 bytes（见 convert_img_sync）
HelpResult = BytesIO | Path | bytes | bytearray | Image.Image


def ensure_icon_dir() -> None:
    """确保 data/MingChaoBQ/icons/ 存在，方便用户往里面放自定义图标"""
    DATA_ICON_DIR.mkdir(parents=True, exist_ok=True)


def find_icon_path(name: str) -> Path | None:
    """查找图标文件，按 data → 插件目录 顺序；都找不到时退回通用图标。"""
    if not name:
        return None

    direct = Path(name)
    if direct.is_absolute() and direct.exists():
        return direct

    for base in (DATA_ICON_DIR, PLUGIN_ICON_DIR):
        path = base / name
        if path.exists():
            return path

    if name != "通用.png":
        for base in (DATA_ICON_DIR, PLUGIN_ICON_DIR):
            fallback = base / "通用.png"
            if fallback.exists():
                return fallback

    return None


def load_icon_image(name: str) -> Image.Image | None:
    """查找并加载图标，返回 PIL.Image 或 None"""
    path = find_icon_path(name)
    if path is None:
        return None
    try:
        return Image.open(path).convert("RGBA")
    except OSError as e:
        logger.warning(f"[MingChaoBQ·图标] 无法加载 {path.name}: {e}")
        return None


def load_bg(config_key: StrKey) -> Image.Image | None:
    """从配置读取背景图文件名，返回 PIL Image 或 None。背景图始终从 data 目录读。"""
    filename = get_str(config_key).strip()
    if not filename:
        return None
    path = BQ_ROOT / filename
    if not path.exists():
        logger.warning(f"[MingChaoBQ·背景] 找不到 {filename}，使用默认背景")
        return None
    try:
        return Image.open(path).convert("RGBA")
    except OSError as e:
        logger.warning(f"[MingChaoBQ·背景] 无法加载 {filename}: {e}")
        return None


def _to_image(result: HelpResult) -> Image.Image:
    if isinstance(result, (bytes, bytearray)):
        return Image.open(BytesIO(result))
    if isinstance(result, BytesIO):
        result.seek(0)
        return Image.open(result)
    if isinstance(result, Path):
        return Image.open(result)
    return result


def compress_result(result: HelpResult, max_width: int = 1200) -> Path:
    """压缩帮助图结果并落缓存目录，返回 Path。"""
    img = _to_image(result)

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    clean_cache()
    if img.mode in ("RGBA", "P", "LA"):
        filepath = new_cache_path("help", ".png")
        img.save(filepath, format="PNG", optimize=True, compress_level=9)
    else:
        filepath = new_cache_path("help", ".jpg")
        img.convert("RGB").save(filepath, format="JPEG", quality=80, optimize=True)
    return filepath


def get_max_width() -> int:
    return get_int("mcbq_image_max_width", 1200)
