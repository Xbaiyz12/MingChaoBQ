"""呜哇小站开放接口：角色 / 画师 / 表情包元数据查询。

只读 JSON，不涉及图片下载（图片由 api_client 走 curl + ticket 拿）。
分页注意：page 从 1 开始（page=0 会失败），size 上限 100。
"""

from typing import TypedDict

import aiohttp

from gsuid_core.logger import logger

SITE_API = "https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games/v1alpha1"
# 站点接口的 size 上限实测为 100，超过直接失败
_MAX_SIZE = 100


class SiteCharacter(TypedDict):
    slug: str
    name: str
    count: int
    packCount: int


class SitePack(TypedDict):
    slug: str
    title: str
    count: int
    artists: list[str]
    characters: list[str]


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _parse_character(raw: object) -> SiteCharacter | None:
    if not isinstance(raw, dict):
        return None
    name = _as_str(raw.get("name"))
    if not name:
        return None
    return SiteCharacter(
        slug=_as_str(raw.get("slug")),
        name=name,
        count=_as_int(raw.get("count")),
        packCount=_as_int(raw.get("packCount")),
    )


def _parse_pack(raw: object) -> SitePack | None:
    if not isinstance(raw, dict):
        return None
    title = _as_str(raw.get("title")).strip()
    if not title:
        return None
    artists: list[str] = []
    for item in raw.get("artists") or []:
        name = _as_str(item.get("name")) if isinstance(item, dict) else ""
        if name:
            artists.append(name)
    characters: list[str] = []
    for item in raw.get("characters") or []:
        name = _as_str(item.get("name")) if isinstance(item, dict) else ""
        if name:
            characters.append(name)
    return SitePack(
        slug=_as_str(raw.get("slug")),
        title=title,
        count=_as_int(raw.get("count")),
        artists=artists,
        characters=characters,
    )


async def _get_json(path: str, params: dict[str, str]) -> object | None:
    url = f"{SITE_API}/{path}"
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"[MingChaoBQ·小站] {path} status={resp.status}")
                    return None
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        logger.warning(f"[MingChaoBQ·小站] {path} 请求失败: {e}")
        return None


async def search_characters(keyword: str, limit: int = 20) -> list[SiteCharacter]:
    """按关键词搜角色，返回匹配项（站点侧就是模糊搜索）。"""
    if not keyword.strip():
        return []
    data = await _get_json("characters", {"q": keyword.strip(), "page": "1", "size": str(min(limit, _MAX_SIZE))})
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [c for c in (_parse_character(item) for item in items) if c is not None]


async def list_characters(limit: int = _MAX_SIZE) -> list[SiteCharacter]:
    """全部角色。"""
    data = await _get_json("characters", {"page": "1", "size": str(min(limit, _MAX_SIZE))})
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [c for c in (_parse_character(item) for item in items) if c is not None]


async def list_packs_by_character(character: str, limit: int = _MAX_SIZE) -> list[SitePack]:
    """某角色相关的全部表情包（站点会带上官方转发包等）。"""
    if not character.strip():
        return []
    data = await _get_json("packs", {"character": character.strip(), "page": "1", "size": str(min(limit, _MAX_SIZE))})
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [p for p in (_parse_pack(item) for item in items) if p is not None]
