"""API 结果的本地落盘：按角色分目录，按图片内容去重。"""

import shutil
import hashlib
from pathlib import Path

from gsuid_core.pool import to_thread

from .api_client import DEFAULT_BASE, DEFAULT_RANDOM_PATH, DEFAULT_CHARACTER_PARAM, ApiPic, BqApiClient
from .utils.paths import BQ_ROOT
from .mingchao_config import get_str, get_bool

API_DIR_NAME = "API"


def safe_name(name: str) -> str:
    """把远端可控的字符串变成安全目录/文件名：去分隔符、去 . 与空白、限长。"""
    cleaned = name
    for ch in '\\/:*?"<>|':
        cleaned = cleaned.replace(ch, "_")
    cleaned = "".join(c for c in cleaned if c.isprintable()).strip().strip(".")
    return cleaned[:64] or "未命名"


def get_client() -> BqApiClient:
    return BqApiClient(
        base_url=get_str("mcbq_api_base") or DEFAULT_BASE,
        token=get_str("mcbq_api_token"),
        random_path=get_str("mcbq_api_random_path") or DEFAULT_RANDOM_PATH,
        character_param=get_str("mcbq_api_character_param") or DEFAULT_CHARACTER_PARAM,
    )


def _save_dir_for(role: str) -> Path:
    return BQ_ROOT / API_DIR_NAME / safe_name(role)


@to_thread
def _file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()[:10]


async def file_md5(path: Path) -> str:
    """文件内容 md5 前 10 位，用于按内容去重（ticket URL 每次都变，不能按 URL 判重）。"""
    return await _file_md5(path)


def clean_tmp_files(root: Path) -> int:
    """清理中断遗留的下载临时文件（超时取消时 finally 来不及跑的历史残留）。"""
    removed = 0
    for path in root.rglob("tmp_*"):
        if path.is_file():
            path.unlink(missing_ok=True)
            removed += 1
    return removed


async def download_to_url(url: str, save_path: Path) -> bool:
    """下载入口，调用方不用自己拼 client。"""
    return await get_client().download(url, save_path)


async def save_api_pic_to_local(data: ApiPic) -> Path | None:
    """
    下载一条 API 结果并保存到本地，返回本地路径或 None。
    URL 是临时 ticket（同一张图每次都不一样），所以只能按图片内容去重，不能按 URL。
    """
    if not get_bool("mcbq_api_save_local"):
        return None

    save_dir = _save_dir_for(data["role"])
    save_dir.mkdir(parents=True, exist_ok=True)

    # 这个 id 已经下过就直接复用，省掉一次完整下载（批量拉取时差别很大）
    stem = safe_name(data["name"])
    existing = next(iter(save_dir.glob(f"{stem}_*")), None)
    if existing is not None:
        return existing

    url = data["url"]
    suffix = data["suffix"]
    tmp_path = save_dir / f"tmp_{hashlib.md5(url.encode('utf-8'), usedforsecurity=False).hexdigest()[:10]}{suffix}"

    try:
        if not await get_client().download(url, tmp_path):
            return None
        digest = await _file_md5(tmp_path)
        final_path = save_dir / f"{safe_name(data['name'])}_{digest}{suffix}"
        if final_path.exists():
            return final_path
        shutil.move(tmp_path, final_path)
        return final_path
    finally:
        # 下载被超时取消时也要清掉临时文件，否则残留会越积越多
        tmp_path.unlink(missing_ok=True)


async def fetch_and_save(role: str = "", artist: str = "", pack: str = "") -> ApiPic | None:
    """从 API 取一张，按配置保存到本地，返回带 saved_path 的记录。"""
    data = await get_client().fetch_random_json(role=role, artist=artist, pack=pack)
    if not data:
        return None

    saved_path = await save_api_pic_to_local(data)
    if saved_path is not None:
        data["saved_path"] = str(saved_path)
    return data
