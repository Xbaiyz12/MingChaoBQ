import hashlib
from pathlib import Path

from .utils.paths import BQ_ROOT
from .api_client import BqApiClient
from .mingchao_config import get_config

API_DIR_NAME = "API"


def _safe_name(name: str) -> str:
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip() or "未命名"


def _get_client() -> BqApiClient:
    base = (
        get_config("mcbq_api_base")
        or "https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games"
    ).strip()
    token = (get_config("mcbq_api_token") or "").strip()
    random_path = (get_config("mcbq_api_random_path") or "/v1alpha1/random").strip()
    char_param = (get_config("mcbq_api_character_param") or "character").strip()
    return BqApiClient(base, token, random_path, char_param)


def _save_dir_for(role: str) -> Path:
    return BQ_ROOT / API_DIR_NAME / _safe_name(role)


def _url_to_filename(url: str, name: str, suffix: str = ".gif") -> str:
    """用 URL 的 hash + 名字生成文件名，避免重名"""
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    safe = _safe_name(name)
    return f"{safe}_{h}{suffix}"


async def save_api_pic_to_local(data: dict) -> Path | None:
    """
    把 API 返回的一条数据下载并保存到本地。
    返回本地路径或 None。
    注意：由于 url 是临时 ticket，必须立刻下载，不能缓存 URL 复用。
    """
    if not get_config("mcbq_api_save_local"):
        return None

    client = _get_client()
    role = _safe_name(data.get("role", "未分类角色"))
    name = data.get("name", "未命名")
    suffix = data.get("suffix", ".gif")
    url = data.get("url", "")
    if not url:
        return None

    filename = _url_to_filename(url, name, suffix)
    save_path = _save_dir_for(role) / filename

    if save_path.exists():
        return save_path

    ok = await client.download(url, save_path)
    return save_path if ok else None


async def fetch_and_save(role: str = "") -> dict | None:
    """
    从 API 获取一张，按配置保存到本地。
    返回 {"url", "name", "role", "saved_path"} 或 None
    """
    client = _get_client()
    data = await client.fetch_random_json(role=role)
    if not data:
        return None

    saved_path = await save_api_pic_to_local(data)
    if saved_path:
        data["saved_path"] = str(saved_path)
    return data