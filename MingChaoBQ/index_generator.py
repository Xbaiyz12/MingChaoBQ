import json
import re
from pathlib import Path

from .utils.paths import BQ_ROOT, INDEX_PATH, SUPPORTED_EXTS

# API 目录的名字，识别这个目录下的图片标记来源为 api
API_DIR_NAME = "API"


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


def _make_pic(file_path: Path, is_api: bool = False) -> dict:
    pic = {
        "file": str(file_path.relative_to(BQ_ROOT)),
        "emotion": _extract_emotion_name(file_path.name),
    }
    if is_api:
        pic["source"] = "api"
    return pic


def generate_index() -> dict:
    """
    扫描 BQ_ROOT 生成索引。
    结构：
      {画师名: {角色名: {子分类名: [pic, ...]}}}
    画师目录下直接是图片时，归到 {画师: {"_default": {"_default": [...]}}}
    API 目录下的图片带 source="api" 标记。
    """
    index = {}

    if not BQ_ROOT.exists():
        raise FileNotFoundError(f"表情包目录不存在: {BQ_ROOT}")

    for artist_dir in sorted(BQ_ROOT.iterdir()):
        if not artist_dir.is_dir():
            continue

        artist_name = artist_dir.name
        if artist_name in ("icons", "cache"):
            continue

        is_api_dir = (artist_name == API_DIR_NAME)
        index[artist_name] = {}

        # 画师目录下直接是图片
        direct_imgs = [
            f for f in artist_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
        ]
        if direct_imgs:
            index[artist_name]["_default"] = {
                "_default": [_make_pic(f, is_api_dir) for f in sorted(direct_imgs)]
            }

        # 角色目录
        for char_dir in sorted(artist_dir.iterdir()):
            if not char_dir.is_dir():
                continue

            char_name = char_dir.name
            sub_dirs = [d for d in char_dir.iterdir() if d.is_dir()]
            imgs_in_char = [
                f for f in char_dir.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
            ]

            if sub_dirs:
                index[artist_name][char_name] = {}
                if imgs_in_char:
                    index[artist_name][char_name]["_default"] = [
                        _make_pic(f, is_api_dir) for f in sorted(imgs_in_char)
                    ]
                for sub_dir in sorted(sub_dirs):
                    imgs = [
                        f for f in sub_dir.iterdir()
                        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
                    ]
                    if imgs:
                        index[artist_name][char_name][sub_dir.name] = [
                            _make_pic(f, is_api_dir) for f in sorted(imgs)
                        ]
            else:
                if imgs_in_char:
                    index[artist_name][char_name] = {
                        "_default": [_make_pic(f, is_api_dir) for f in sorted(imgs_in_char)]
                    }

    return index


def save_index(index: dict):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def load_index() -> dict:
    if not INDEX_PATH.exists():
        index = generate_index()
        save_index(index)
        return index
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)