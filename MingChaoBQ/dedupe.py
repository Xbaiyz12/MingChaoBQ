"""表情包查重：内容帧指纹 → 16x16 dHash 全库比对 → 并查集分组。

两个关键设计，都来自真实库上的实测：
1. 取「内容最丰富的一帧」而不是第 0 帧：很多 GIF 开头是淡入空白帧，拿第 0 帧
   比对会把整库"空白首帧"的图判成同一张（实测直接炸出 1768 张一组的误报）。
2. 用 16x16 dHash（256 位）而不是 ORB / 像素比对：
   - ORB 单应性在同一角色换表情时也给出 1.0 相似度，区分不了"重复"和"同模板"；
   - 像素比对对线条锐利的表情画不成立（缩放 80% 后线条错位，真重复差异也能到 52%）；
   - dHash16 实测：真重复最大汉明距离 5，不同图最小 32，中间空档极大。
"""

import json
import time
import asyncio
from typing import TypedDict
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from .utils.paths import BQ_ROOT
from .index_generator import load_index
from .utils.index_types import Index

# 16x16 = 256 位，判重阈值：实测真重复 ≤5、不同图 ≥32，取中间偏严
_HASH_N = 16
_HAMMING_MAX = 16

# 动图最多扫多少帧去找内容最丰富的那帧
_MAX_SCAN_FRAMES = 24
# 某帧边缘能量达到这个值就算内容够丰富，不再往后扫
_CONTENT_ENOUGH = 8.0
# 边缘能量低于此值视为纯色/空白帧（全黑帧同样算空白）
_CONTENT_BLANK = 0.5

_HASH_BATCH = 200
_CACHE_PATH = BQ_ROOT / "dedupe_hash.json"
# 缓存格式版本：指纹算法改动时 +1，避免沿用旧值
_CACHE_VERSION = 3
# 缓存 key 的分隔符：文件名里不可能出现这个控制字符，路径带 | 也不会切错
_SEP = "\x1f"


class DupItem(TypedDict):
    file: str
    artist: str
    char: str
    emotion: str
    size: int


class DupGroup(TypedDict):
    items: list[DupItem]
    keep: str
    dup_size: int


class DupReport(TypedDict):
    scanned: int
    groups: list[DupGroup]
    total_items: int
    waste_size: int
    plain_skipped: int


def default_hamming_max() -> int:
    return _HAMMING_MAX


def _cache_key(item: DupItem) -> str:
    """版本 + 路径 + mtime + 大小，任一变化就重算指纹。"""
    stat = (BQ_ROOT / item["file"]).stat()
    return _SEP.join((f"v{_CACHE_VERSION}", item["file"], str(int(stat.st_mtime)), str(item["size"])))


def _file_of(key: str) -> str:
    return key.split(_SEP)[1]


def _flatten(image: Image.Image) -> Image.Image:
    """透明底铺白，避免透明像素被当成黑色，让不同图的留白区看起来一样。"""
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")
    return image.convert("RGB")


def _content_score(image: Image.Image) -> float:
    """帧的内容复杂度 = 相邻像素差分均值。纯色帧（含全黑帧）接近 0。

    不能用「非白像素占比」：全黑帧的非白占比是 100%，会被误判成内容最丰富的帧，
    实测正是它让一堆黑帧互相撞成「重复」（同一动作的 GIF 开头常是纯黑帧）。
    """
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    if gray.shape[0] < 2 or gray.shape[1] < 2:
        return 0.0
    return float(np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean())


def _crop_content(image: Image.Image) -> Image.Image:
    """裁掉四周纯白留白，让同一张图带不带白边都得到同一个指纹。"""
    white = Image.new("RGB", image.size, (255, 255, 255))
    bbox = ImageChops.difference(image, white).getbbox()
    if bbox is None or bbox[2] - bbox[0] < 16 or bbox[3] - bbox[1] < 16:
        return image
    return image.crop(bbox)


def read_content_frame(path: Path) -> tuple[Image.Image, float] | None:
    """读「内容最丰富的一帧」。返回 (图, 内容分数)。查重与报告缩略图共用。"""
    try:
        with Image.open(path) as image:
            frames = getattr(image, "n_frames", 1)
            if frames <= 1:
                image.load()
                flat = _flatten(image)
                return flat, _content_score(flat)

            best: Image.Image | None = None
            best_score = -1.0
            step = max(1, frames // _MAX_SCAN_FRAMES)
            for index in range(0, frames, step):
                image.seek(index)
                candidate = _flatten(image)
                score = _content_score(candidate)
                if score > best_score:
                    best, best_score = candidate, score
                if best_score >= _CONTENT_ENOUGH:
                    break
            if best is None:
                image.seek(0)
                best = _flatten(image)
                best_score = _content_score(best)
            return best, best_score
    except (OSError, ValueError) as e:
        logger.debug(f"[MingChaoBQ·查重] 无法读取 {path.name}: {e}")
        return None


def _dhash(image: Image.Image) -> int:
    """裁留白后做 16x16 差分哈希（256 位）。"""
    small = _crop_content(image).convert("L").resize((_HASH_N + 1, _HASH_N), Image.LANCZOS)
    pixels = np.asarray(small, dtype=np.int16)
    value = 0
    for bit in (pixels[:, 1:] > pixels[:, :-1]).flatten():
        value = (value << 1) | int(bit)
    return value


@to_thread
def _iter_local_pics(index: Index) -> list[DupItem]:
    """索引里的本地图（含 API 目录），带上画师/角色/表情名便于报告里定位。"""
    items: list[DupItem] = []
    for artist, chars in index.items():
        for char, subcats in chars.items():
            for pics in subcats.values():
                for pic in pics:
                    path = BQ_ROOT / pic["file"]
                    if not path.exists():
                        continue
                    items.append(
                        DupItem(
                            file=pic["file"],
                            artist=artist,
                            char=char if char != "_default" else "",
                            emotion=pic.get("emotion", ""),
                            size=path.stat().st_size,
                        )
                    )
    return items


@to_thread
def _read_cache() -> dict[str, int]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        raw: object = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("[MingChaoBQ·查重] 指纹缓存损坏，本次重新计算")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, int)}


@to_thread
def _write_cache(hashes: dict[str, int]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _CACHE_PATH.with_name(_CACHE_PATH.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False)
    tmp_path.replace(_CACHE_PATH)


@to_thread
def _hash_one(item: DupItem) -> tuple[str, int, bool] | None:
    """单张图的 dHash。解码（含挑帧）是唯一的重活，放线程池跑。

    整张图都几乎没有内容（纯色/全黑）时不返回指纹 —— 这类图互相之间天然"哈希相同"，
    放进比对池只会制造误报。
    """
    read = read_content_frame(BQ_ROOT / item["file"])
    if read is None:
        return None
    image, score = read
    return _cache_key(item), _dhash(image), score < _CONTENT_BLANK


async def _hash_all(items: list[DupItem], cached: dict[str, int]) -> tuple[dict[str, int], int, int]:
    """算 dHash，缓存命中直接复用；只有新图/改动过的图才解码。"""
    hashes: dict[str, int] = {}
    pending: list[DupItem] = []
    for item in items:
        key = _cache_key(item)
        if key in cached:
            hashes[key] = cached[key]
        else:
            pending.append(item)

    computed = 0
    plain = 0
    for start in range(0, len(pending), _HASH_BATCH):
        batch = await asyncio.gather(*(_hash_one(item) for item in pending[start : start + _HASH_BATCH]))
        for hit in batch:
            if hit is None:
                continue
            if hit[2]:
                plain += 1
                continue
            hashes[hit[0]] = hit[1]
            computed += 1
    return hashes, computed, plain


@to_thread
def _find_pairs(keys: list[str], hashes: dict[str, int], threshold: int) -> list[tuple[str, str]]:
    """两两比汉明距离。256 位哈希是 Python 大整数，异或后数 1 即可，n=几千时够快。"""
    pairs: list[tuple[str, str]] = []
    for index, first in enumerate(keys):
        value = hashes[first]
        for second in keys[index + 1 :]:
            if (value ^ hashes[second]).bit_count() <= threshold:
                pairs.append((first, second))
    return pairs


class _UnionFind:
    def __init__(self, keys: list[str]) -> None:
        self._parent = {key: key for key in keys}
        self._rank = dict.fromkeys(keys, 0)

    def find(self, key: str) -> str:
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, first: str, second: str) -> None:
        root_a, root_b = self.find(first), self.find(second)
        if root_a == root_b:
            return
        if self._rank[root_a] < self._rank[root_b]:
            root_a, root_b = root_b, root_a
        self._parent[root_b] = root_a
        if self._rank[root_a] == self._rank[root_b]:
            self._rank[root_a] += 1


@to_thread
def _build_groups(items: dict[str, DupItem], pairs: list[tuple[str, str]]) -> list[DupGroup]:
    """把两两「同一张图」的关系并成组，并挑出建议保留的那张。"""
    keys = sorted({key for pair in pairs for key in pair})
    if not keys:
        return []
    union = _UnionFind(keys)
    for first, second in pairs:
        union.union(first, second)

    buckets: dict[str, list[str]] = {}
    for key in keys:
        buckets.setdefault(union.find(key), []).append(key)

    groups: list[DupGroup] = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=_file_of)
        keep = max(ordered, key=lambda key: items[key]["size"])
        smallest = min(items[key]["size"] for key in ordered)
        groups.append(
            DupGroup(
                items=[items[key] for key in ordered],
                keep=_file_of(keep),
                # 每删一张至少能省下组内最小那张的体积，给个保守估计
                dup_size=(len(ordered) - 1) * smallest,
            )
        )
    groups.sort(key=lambda group: (-len(group["items"]), group["keep"]))
    return groups


async def scan_duplicates(threshold: int = _HAMMING_MAX) -> DupReport:
    """全库查重。指纹有缓存，第二次跑基本只剩新增图的解码成本。"""
    started = time.time()
    index = await load_index()
    items_list = await _iter_local_pics(index)
    if not items_list:
        return DupReport(scanned=0, groups=[], total_items=0, waste_size=0, plain_skipped=0)

    items = {_cache_key(item): item for item in items_list}
    cached = await _read_cache()
    hashes, computed, plain = await _hash_all(items_list, cached)
    if computed:
        await _write_cache(hashes)

    pairs = await _find_pairs(list(hashes), hashes, threshold)
    groups = await _build_groups(items, pairs)

    logger.info(
        f"[MingChaoBQ·查重] 扫描 {len(items)} 张（新算 {computed}，空白跳过 {plain}，候选 {len(pairs)} 对），"
        f"发现 {len(groups)} 组，耗时 {time.time() - started:.1f}s"
    )
    return DupReport(
        scanned=len(items),
        groups=groups,
        total_items=sum(len(group["items"]) for group in groups),
        waste_size=sum(group["dup_size"] for group in groups),
        plain_skipped=plain,
    )
