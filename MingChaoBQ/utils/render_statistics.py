"""MingChaoBQ 统计图渲染。"""

import asyncio
from pathlib import Path

from PIL import Image

from gsuid_core.utils.image.image_tools import get_qq_avatar

from ..statistics import StatsData
from .render_rank import MAX_ROWS, render_rank, sorted_rows


async def _load_avatars(users: dict[str, str]) -> dict[str, Image.Image]:
    """优先用平台/库里的头像 URL，取不到再按 QQ 号拿 qlogo（URL 会过期）。"""

    async def fetch(key: str, url: str) -> Image.Image | None:
        if url:
            image = await get_qq_avatar(None, url)
            if image is not None:
                return image
        return await get_qq_avatar(key)

    if not users:
        return {}
    results = await asyncio.gather(*(fetch(key, url) for key, url in users.items()))
    return {key: image for key, image in zip(users, results, strict=True) if image is not None}


async def render_poke_statistics(data: StatsData) -> Path:
    """渲染被戳总次数与用户排行（头像 + 昵称，昵称下方为 QQ 号）。"""
    rows = [(key, value["count"]) for key, value in data["poke_users"].items()]
    labels = {key: (value["name"], key) for key, value in data["poke_users"].items()}
    top_keys = [key for key, _ in sorted_rows(rows)[:MAX_ROWS]]
    avatars = await _load_avatars({key: data["poke_users"][key]["avatar"] for key in top_keys})
    return await render_rank("戳一戳统计", rows, "poke-stats", "次", labels, avatars)


async def render_role_statistics(data: StatsData) -> Path:
    """渲染角色名发送排行。"""
    return await render_rank("角色表情发送统计", list(data["roles"].items()), "role-stats", "次")
