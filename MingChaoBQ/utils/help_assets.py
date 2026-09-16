import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from .paths import BQ_ROOT
from ..mingchao_config import get_config

# 插件根目录：plugins/MingChaoBQ/
PLUGIN_ROOT = Path(__file__).parent.parent.parent

# 插件自带的默认图标目录（随 GitHub 仓库走）
PLUGIN_ICON_DIR = PLUGIN_ROOT / "MingChaoBQ" / "icons"

# 用户自定义图标目录（可选覆盖）
DATA_ICON_DIR = BQ_ROOT / "icons"

# 插件主图标（帮助图顶部那个）
PLUGIN_ICON = PLUGIN_ROOT / "ICON.png"


def ensure_icon_dir():
    """确保 data/MingChaoBQ/icons/ 存在，方便用户往里面放自定义图标"""
    DATA_ICON_DIR.mkdir(parents=True, exist_ok=True)


def find_icon_path(name: str):
    """
    查找图标文件，按 data → 插件目录 顺序。
    返回 Path 或 None。
    """
    if not name:
        return None

    # 绝对路径直接用
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p

    # data 目录优先
    data_path = DATA_ICON_DIR / name
    if data_path.exists():
        return data_path

    # 插件目录
    plugin_path = PLUGIN_ICON_DIR / name
    if plugin_path.exists():
        return plugin_path

    # 兜底通用图标
    if name != "通用.png":
        for cand in (DATA_ICON_DIR / "通用.png", PLUGIN_ICON_DIR / "通用.png"):
            if cand.exists():
                return cand

    return None


def load_icon_image(name: str):
    """查找并加载图标，返回 PIL.Image 或 None"""
    path = find_icon_path(name)
    if path is None:
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def load_bg(config_key: str):
    """从配置读取背景图，返回 PIL Image 或 None。背景图仍从 data 目录读。"""
    filename = (get_config(config_key) or "").strip()
    if not filename:
        return None
    path = BQ_ROOT / filename
    if not path.exists():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def compress_result(result, max_width: int = 1200) -> Path:
    """压缩帮助图结果，保存到缓存文件，返回 Path。"""
    if isinstance(result, BytesIO):
        result.seek(0)
        img = Image.open(result)
    elif isinstance(result, Path):
        img = Image.open(result)
    elif isinstance(result, (bytes, bytearray)):
        img = Image.open(BytesIO(result))
    elif isinstance(result, Image.Image):
        img = result
    else:
        return result

    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    cache_dir = BQ_ROOT / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        now = time.time()
        for f in cache_dir.iterdir():
            if f.is_file() and now - f.stat().st_mtime > 3600:
                f.unlink(missing_ok=True)
    except Exception:
        pass

    filepath = cache_dir / f"overview_{int(time.time() * 1000)}.png"
    if img.mode in ("RGBA", "P", "LA"):
        img.save(filepath, format="PNG", optimize=True, compress_level=9)
    else:
        img.convert("RGB").save(filepath, format="JPEG", quality=80, optimize=True)
    return filepath


def get_max_width() -> int:
    try:
        return int((get_config("mcbq_image_max_width") or "1200").strip() or 1200)
    except Exception:
        return 1200