"""扫描表情包目录生成索引，并带 mtime 缓存（index.json 接近 1MB，不能每条消息重解析）。"""

import re
import json
import asyncio
from pathlib import Path

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from .utils.paths import BQ_ROOT, INDEX_PATH, SUPPORTED_EXTS
from .utils.index_types import Index, CharMap, SubCats, PicEntry

# API 目录的名字，识别这个目录下的图片标记来源为 api
API_DIR_NAME = "API"

# 不参与索引的目录
_SKIP_DIRS = {"icons", "cache"}

_cached_mtime: float = -1.0
_cached_index: Index | None = None


def _extract_emotion_name(filename: str) -> str:
    """从文件名提取表情名"""
    stem = Path(filename).stem

    m = re.match(r"^\d+-\w+?_(.+?)(?:_\d{4}-\d{2}-\d{2}.*)?$", stem)
    if m:
        return m.group(1).strip()

    m = re.match(r"^\d+-(\d*)(.+)$", stem)
    if m:
        name = m.group(2).strip()
        if name:
            return name

    m = re.match(r"^[A-Z]+\d*_(.+)$", stem)
    if m:
        return m.group(1).strip()

    m = re.match(r"^\d+\s*(.+)$", stem)
    if m:
        return m.group(1).strip()

    return stem


def _make_pic(file_path: Path, is_api: bool = False) -> PicEntry:
    pic = PicEntry(file=str(file_path.relative_to(BQ_ROOT)), emotion=_extract_emotion_name(file_path.name))
    if is_api:
        pic["source"] = "api"
    return pic


def _list_imgs(directory: Path) -> list[Path]:
    return sorted(f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS)


def generate_index() -> Index:
    """
    扫描 BQ_ROOT 生成索引。
    结构：
      {画师名: {角色名: {子分类名: [pic, ...]}}}
    画师目录下直接是图片时，归到 {画师: {"_default": {"_default": [...]}}}
    API 目录下的图片带 source="api" 标记。
    """
    index: Index = {}

    if not BQ_ROOT.exists():
        raise FileNotFoundError(f"表情包目录不存在: {BQ_ROOT}")

    for artist_dir in sorted(BQ_ROOT.iterdir()):
        if not artist_dir.is_dir() or artist_dir.name in _SKIP_DIRS:
            continue

        artist_name = artist_dir.name
        is_api_dir = artist_name == API_DIR_NAME
        char_map: CharMap = {}

        # 画师目录下直接是图片
        direct_imgs = _list_imgs(artist_dir)
        if direct_imgs:
            char_map["_default"] = {"_default": [_make_pic(f, is_api_dir) for f in direct_imgs]}

        # 角色目录
        for char_dir in sorted(artist_dir.iterdir()):
            if not char_dir.is_dir():
                continue

            imgs_in_char = _list_imgs(char_dir)
            sub_dirs = sorted(d for d in char_dir.iterdir() if d.is_dir())

            if sub_dirs:
                sub_map: SubCats = {}
                if imgs_in_char:
                    sub_map["_default"] = [_make_pic(f, is_api_dir) for f in imgs_in_char]
                for sub_dir in sub_dirs:
                    imgs = _list_imgs(sub_dir)
                    if imgs:
                        sub_map[sub_dir.name] = [_make_pic(f, is_api_dir) for f in imgs]
                if sub_map:
                    char_map[char_dir.name] = sub_map
            elif imgs_in_char:
                char_map[char_dir.name] = {"_default": [_make_pic(f, is_api_dir) for f in imgs_in_char]}

        if char_map:
            index[artist_name] = char_map

    return index


def _parse_pic(value: object) -> PicEntry | None:
    if not isinstance(value, dict):
        return None
    file = value.get("file")
    emotion = value.get("emotion")
    if not isinstance(file, str) or not isinstance(emotion, str):
        return None
    pic = PicEntry(file=file, emotion=emotion)
    source = value.get("source")
    if isinstance(source, str):
        pic["source"] = source
    return pic


def _parse_index(raw: object) -> Index:
    """把磁盘上的 JSON 收敛成 Index，结构不对的条目直接丢掉而不是让后续检索崩掉。"""
    if not isinstance(raw, dict):
        return {}

    index: Index = {}
    for artist, chars in raw.items():
        if not isinstance(artist, str) or not isinstance(chars, dict):
            continue
        char_map: CharMap = {}
        for char, subcats in chars.items():
            if not isinstance(char, str) or not isinstance(subcats, dict):
                continue
            sub_map: SubCats = {}
            for sub_name, pics in subcats.items():
                if not isinstance(sub_name, str) or not isinstance(pics, list):
                    continue
                parsed = [pic for pic in (_parse_pic(p) for p in pics) if pic is not None]
                if parsed:
                    sub_map[sub_name] = parsed
            if sub_map:
                char_map[char] = sub_map
        if char_map:
            index[artist] = char_map
    return index


def _mtime() -> float:
    try:
        return INDEX_PATH.stat().st_mtime
    except OSError:
        return -1.0


def _remember(index: Index, mtime: float) -> None:
    global _cached_mtime, _cached_index
    _cached_index = index
    _cached_mtime = mtime


def save_index(index: Index) -> None:
    """先写临时文件再替换，避免写一半留下坏索引。"""
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = INDEX_PATH.with_name(INDEX_PATH.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    tmp_path.replace(INDEX_PATH)
    _remember(index, _mtime())


@to_thread
def _scan_and_save() -> Index:
    """全量重扫 + 落盘。目录迭代与 1MB 写入都是阻塞操作，放线程池。"""
    index = generate_index()
    save_index(index)
    return index


async def rebuild_index() -> Index:
    return await _scan_and_save()


async def load_index() -> Index:
    """读索引。文件 mtime 没变就直接复用上次解析结果。"""
    if not INDEX_PATH.exists():
        return await rebuild_index()

    mtime = _mtime()
    if _cached_index is not None and mtime == _cached_mtime:
        return _cached_index

    def _read_index_file() -> object:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    try:
        raw: object = await asyncio.to_thread(_read_index_file)
    except (OSError, ValueError):
        # 索引文件是外部可改的，损坏时重新生成而不是把异常抛进命令里
        logger.warning("[MingChaoBQ·索引] index.json 无法读取，重新生成")
        return await rebuild_index()

    index = _parse_index(raw)
    _remember(index, mtime)
    return index
