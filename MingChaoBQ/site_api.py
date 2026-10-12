"""呜哇小站开放接口：角色 / 画师 / 表情包元数据查询。

只读 JSON，不涉及图片下载（图片由 api_client 走 curl + ticket 拿）。
分页注意：page 从 1 开始（page=0 会失败），size 上限 100。
"""

from typing import TypedDict

import aiohttp

from gsuid_core.logger import logger

SITE_API = "https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games/v1alpha1"
# 站点接口的 size 上限：characters/artists/packs 是 100，emojis 是 50
_MAX_SIZE = 100
_EMOJI_MAX_SIZE = 50


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


class SiteArtist(TypedDict):
    slug: str
    name: str
    count: int
    packCount: int


class SiteEmoji(TypedDict):
    """emojis 接口返回的一条表情记录，url 是带一次性 ticket 的下载地址。"""

    id: str
    url: str
    format: str
    character: str
    artist: str
    pack_title: str


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


def _parse_artist(raw: object) -> SiteArtist | None:
    if not isinstance(raw, dict):
        return None
    name = _as_str(raw.get("name"))
    if not name:
        return None
    return SiteArtist(
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


async def list_artists(limit: int = _MAX_SIZE) -> list[SiteArtist]:
    """全部画师（含各自表情数与包数）。"""
    data = await _get_json("artists", {"page": "1", "size": str(min(limit, _MAX_SIZE))})
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [a for a in (_parse_artist(item) for item in items) if a is not None]


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


def _names(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        name = _as_str(item.get("name")) if isinstance(item, dict) else ""
        if name:
            out.append(name)
    return out


def _parse_emoji(raw: object) -> SiteEmoji | None:
    if not isinstance(raw, dict):
        return None
    url = _as_str(raw.get("url"))
    if not url:
        return None
    pack = raw.get("pack")
    pack_title = _as_str(pack.get("title")).strip() if isinstance(pack, dict) else ""
    characters = _names(raw.get("characters"))
    artists = _names(raw.get("artists"))
    return SiteEmoji(
        id=_as_str(raw.get("id")),
        url=url,
        format=_as_str(raw.get("format")),
        character=characters[0] if characters else "",
        artist=artists[0] if artists else "",
        pack_title=pack_title,
    )


async def list_emojis(
    character: str = "",
    artist: str = "",
    page: int = 1,
    size: int = _EMOJI_MAX_SIZE,
) -> list[SiteEmoji]:
    """按角色 / 画师（可同时给，返回同时满足的）列出表情，附带可直接下载的 ticket URL。

    emojis 的 size 上限是 50（与 characters 的 100 不同），超出会失败。
    """
    params: dict[str, str] = {"page": str(max(1, page)), "size": str(min(size, _EMOJI_MAX_SIZE))}
    if character.strip():
        params["character"] = character.strip()
    if artist.strip():
        params["artist"] = artist.strip()
    if len(params) <= 2:
        return []

    data = await _get_json("emojis", params)
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [e for e in (_parse_emoji(item) for item in items) if e is not None]
