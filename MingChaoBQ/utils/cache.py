"""插件缓存目录：所有临时图的统一出口 + 过期清理。"""

import time
import itertools
from pathlib import Path

from gsuid_core.logger import logger

from .paths import BQ_ROOT

CACHE_DIR = BQ_ROOT / "cache"
CACHE_TTL = 3600

_seq = itertools.count()


def clean_cache(ttl: int = CACHE_TTL) -> None:
    """删掉超过 ttl 秒的缓存文件。单个文件删不掉（被占用）不影响其余流程。"""
    if not CACHE_DIR.exists():
        return
    now = time.time()
    for item in CACHE_DIR.iterdir():
        if not item.is_file():
            continue
        try:
            if now - item.stat().st_mtime > ttl:
                item.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"[MingChaoBQ·缓存] 删除失败 {item.name}: {e}")


def new_cache_path(prefix: str, suffix: str = ".png") -> Path:
    """生成唯一缓存文件名，避免同一毫秒内多次渲染互相覆盖。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{prefix}_{int(time.time() * 1000)}_{next(_seq)}{suffix}"
