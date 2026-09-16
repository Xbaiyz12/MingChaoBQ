import json
import re
from pathlib import Path

from .utils.paths import BQ_ROOT, INDEX_PATH, SUPPORTED_EXTS


def _extract_emotion_name(filename: str) -> str:
    """
    从文件名中提取表情名称。支持多种常见命名格式。
    """
    stem = Path(filename).stem

    # 模式1: 数字-编号_名称 (最常见)
    # 例如 "001-2N04_鹦鹉摇" "001-340_爱心 1_2026-07-01"
    m = re.match(r"^\d+-\w+?_(.+?)(?:_\d{4}-\d{2}-\d{2}.*)?$", stem)
    if m:
        return m.group(1).strip()

    # 模式2: 数字-名称 (例如 "001-1爱心")
    m = re.match(r"^\d+-(\d*)(.+)$", stem)
    if m:
        name = m.group(2).strip()
        if name:
            return name

    # 模式3: 字母编号_名称 (例如 "D10游泳" "DLC1" "XXS01_喇叭")
    m = re.match(r"^[A-Z]+\d*_(.+)$", stem)
    if m:
        return m.group(1).strip()

    # 模式4: 纯中文/字母名称 (例如 "比心" "yes" "上吊")
    m = re.match(r"^\d+\s*(.+)$", stem)
    if m:
        return m.group(1).strip()

    return stem


def generate_index() -> dict:
    """
    扫描 BQ_ROOT 生成索引。
    返回结构：
    {
      "画师名": {
        "角色名": {
          "子分类名": [{"file": "相对路径", "emotion": "表情名"}, ...]
        }
      }
    }
    如果画师目录下直接是图片（没有角色文件夹），
    会归到 "画师名" -> "_default" -> "_default" 里。
    """
    index = {}

    if not BQ_ROOT.exists():
        raise FileNotFoundError(f"表情包目录不存在: {BQ_ROOT}")

    for artist_dir in sorted(BQ_ROOT.iterdir()):
        if not artist_dir.is_dir():
            continue

        artist_name = artist_dir.name
        # 跳过插件自己的数据目录，避免被当作画师
        if artist_name in ("icons", "cache"):
            continue

        index[artist_name] = {}

        # ============ 第一步：处理直接放在画师目录下的散图 ============
        direct_imgs = [
            f for f in artist_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
        ]
        if direct_imgs:
            index[artist_name]["_default"] = {
                "_default": [
                    {
                        "file": str(f.relative_to(BQ_ROOT)),
                        "emotion": _extract_emotion_name(f.name),
                    }
                    for f in sorted(direct_imgs)
                ]
            }

        # ============ 第二步：处理角色文件夹 ============
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
                # 有子分类
                index[artist_name][char_name] = {}
                if imgs_in_char:
                    index[artist_name][char_name]["_default"] = [
                        {
                            "file": str(f.relative_to(BQ_ROOT)),
                            "emotion": _extract_emotion_name(f.name),
                        }
                        for f in sorted(imgs_in_char)
                    ]
                for sub_dir in sorted(sub_dirs):
                    sub_name = sub_dir.name
                    imgs = [
                        f for f in sub_dir.iterdir()
                        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
                    ]
                    if imgs:
                        index[artist_name][char_name][sub_name] = [
                            {
                                "file": str(f.relative_to(BQ_ROOT)),
                                "emotion": _extract_emotion_name(f.name),
                            }
                            for f in sorted(imgs)
                        ]
            else:
                # 没有子分类，直接是图片
                if imgs_in_char:
                    index[artist_name][char_name] = {
                        "_default": [
                            {
                                "file": str(f.relative_to(BQ_ROOT)),
                                "emotion": _extract_emotion_name(f.name),
                            }
                            for f in sorted(imgs_in_char)
                        ]
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