"""呜哇小站列表图渲染：画师榜与搜索结果。"""

from pathlib import Path

from ..site_api import SitePack, SiteArtist, SiteCharacter
from .render_rank import render_rank

_MAX_ARTIST_ROWS = 30
_MAX_PACK_ROWS = 12


def _pack_rows(packs: list[SitePack]) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for pack in packs:
        artist = "/".join(pack["artists"][:2]) or "官方转发"
        rows.append((f"{pack['title'].strip()} · {artist}", pack["count"]))
    return rows


async def render_site_artists(artists: list[SiteArtist]) -> Path:
    """小站画师榜（按表情数降序）。"""
    rows = [(item["name"], item["count"]) for item in artists][:_MAX_ARTIST_ROWS]
    labels = {item["name"]: (item["name"], f"{item['packCount']} 个表情包") for item in artists}
    return await render_rank("呜哇小站 · 画师榜", rows, "site-artists", "张", labels)


async def render_site_search(keyword: str, chars: list[SiteCharacter], packs: list[SitePack]) -> Path:
    """搜索结果：角色与相关表情包放在同一张榜里，角色在前。"""
    rows: list[tuple[str, int]] = []
    labels: dict[str, tuple[str, str]] = {}
    for char in chars:
        key = f"角色 · {char['name']}"
        rows.append((key, char["count"]))
        labels[key] = (char["name"], f"{char['packCount']} 个包")
    for item in _pack_rows(packs[:_MAX_PACK_ROWS]):
        rows.append(item)
        labels[item[0]] = (item[0], "表情包")
    return await render_rank(f"呜哇小站 · 搜索「{keyword}」", rows, "site-search", "张", labels)
