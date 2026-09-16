from pathlib import Path

from .utils.paths import BQ_ROOT, SUPPORTED_EXTS
from .api_client import BqApiClient
from .mingchao_config import get_config


def _safe_name(name: str) -> str:
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip() or "未命名"


def _build_config() -> dict:
    headers_raw = get_config("mcbq_api_headers") or []
    headers = {}
    for line in headers_raw:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()

    return {
        "base_url": (get_config("mcbq_api_url") or "").strip(),
        "token": (get_config("mcbq_api_token") or "").strip(),
        "list_path": (get_config("mcbq_api_list_path") or "/list").strip(),
        "method": (get_config("mcbq_api_method") or "GET").strip(),
        "headers": headers,
        "data_path": (get_config("mcbq_api_data_path") or "").strip(),
        "artist_field": (get_config("mcbq_api_artist_field") or "artist").strip(),
        "char_field": (get_config("mcbq_api_char_field") or "character").strip(),
        "name_field": (get_config("mcbq_api_name_field") or "name").strip(),
        "url_field": (get_config("mcbq_api_url_field") or "url").strip(),
    }


async def sync_from_api() -> dict:
    """
    从 API 拉取全部图片并归档到本地。
    返回 {"total", "success", "failed", "skipped"}
    """
    config = _build_config()
    if not config["base_url"]:
        raise ValueError("API 地址未配置，请在网页控制台填写")

    client = BqApiClient(config)
    items = await client.fetch_all()

    stats = {"total": len(items), "success": 0, "failed": 0, "skipped": 0}

    for item in items:
        artist = _safe_name(item["artist"])
        character = _safe_name(item["character"])
        name = _safe_name(item["name"])
        url = item["url"]

        if not url:
            stats["failed"] += 1
            continue

        suffix = Path(url.split("?")[0]).suffix.lower()
        if suffix not in SUPPORTED_EXTS:
            suffix = ".gif"

        save_path = BQ_ROOT / artist / character / f"{name}{suffix}"

        if save_path.exists():
            stats["skipped"] += 1
            continue

        ok = await client.download(url, save_path)
        if ok:
            stats["success"] += 1
        else:
            stats["failed"] += 1

    return stats