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


async def render_site_artists(artists: list[SiteArtist], local_counts: dict[str, int] | None = None) -> Path:
    """小站画师榜：本地已有的一律排到最前面，组内按表情数降序。

    local_counts 是「本地已有的画师 -> 张数」，命中就整行高亮并标注已有多少张，
    没命中的行暗淡并标注「需拉取」。
    """
    local = local_counts or {}
    ordered = sorted(
        artists,
        key=lambda a: (0 if local.get(a["name"], 0) > 0 else 1, -a["count"], a["name"]),
    )[:_MAX_ARTIST_ROWS]

    rows: list[tuple[str, int]] = []
    labels: dict[str, tuple[str, str]] = {}
    dim: set[str] = set()
    have = 0
    for item in ordered:
        name = item["name"]
        rows.append((name, item["count"]))
        mine = local.get(name, 0)
        if mine > 0:
            have += 1
            labels[name] = (name, f"{item['packCount']} 个包 · 本地已有 {mine} 张")
        else:
            dim.add(name)
            labels[name] = (name, f"{item['packCount']} 个包 · 需拉取")
    extra = f"本地已有 {have} 位 · 需拉取 {len(rows) - have} 位"
    return await render_rank("呜哇小站 · 画师榜", rows, "site-artists", "张", labels, None, dim, extra, keep_order=True)


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
