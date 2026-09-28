"""MingChaoBQ 的戳一戳与角色发送统计。"""

import json
import asyncio
from typing import TypedDict

import aiofiles

from gsuid_core.logger import logger

from .utils.paths import BQ_ROOT

_STATS_PATH = BQ_ROOT / "statistics.json"
_STATS_LOCK = asyncio.Lock()


class PokeUser(TypedDict):
    count: int
    name: str
    avatar: str


class StatsData(TypedDict):
    poke_users: dict[str, PokeUser]
    roles: dict[str, int]


def _empty_stats() -> StatsData:
    return {"poke_users": {}, "roles": {}}


def _read_poke_users(raw: object) -> dict[str, PokeUser]:
    """旧版为 {qq: 次数}，新版为 {qq: {count, name, avatar}}，两种都读得进来。"""
    if not isinstance(raw, dict):
        return {}
    users: dict[str, PokeUser] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            if value >= 0:
                users[key] = {"count": value, "name": key, "avatar": ""}
            continue
        if not isinstance(value, dict):
            continue
        count: object = value["count"] if "count" in value else 0
        name: object = value["name"] if "name" in value else key
        avatar: object = value["avatar"] if "avatar" in value else ""
        if isinstance(count, int) and count >= 0 and isinstance(name, str) and isinstance(avatar, str):
            users[key] = {"count": count, "name": name, "avatar": avatar}
    return users


def _read_roles(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    roles: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            roles[key] = value
    return roles


def _read_stats(raw: object) -> StatsData:
    if not isinstance(raw, dict):
        return _empty_stats()
    users_raw: object = raw["poke_users"] if "poke_users" in raw else {}
    roles_raw: object = raw["roles"] if "roles" in raw else {}
    return {"poke_users": _read_poke_users(users_raw), "roles": _read_roles(roles_raw)}


async def _load() -> StatsData:
    if not _STATS_PATH.exists():
        return _empty_stats()
    async with aiofiles.open(_STATS_PATH, encoding="utf-8") as file:
        content = await file.read()
    if not content.strip():
        return _empty_stats()
    try:
        raw: object = json.loads(content)
    except json.JSONDecodeError as e:
        # 文件被手改或写坏时不能连累戳一戳回图，按空统计继续
        logger.warning(f"[MingChaoBQ·统计] statistics.json 无法解析，按空统计处理: {e}")
        return _empty_stats()
    return _read_stats(raw)


async def _save(data: StatsData) -> None:
    _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _STATS_PATH.with_suffix(".tmp")
    async with aiofiles.open(temp_path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(data, ensure_ascii=False, indent=2))
    temp_path.replace(_STATS_PATH)


async def record_poke(user_id: str, name: str, avatar: str) -> None:
    """记录一次被戳：累计总次数，并刷新该用户的昵称与头像。"""
    key = user_id.strip()
    if not key:
        return
    async with _STATS_LOCK:
        data = await _load()
        user = data["poke_users"][key] if key in data["poke_users"] else PokeUser(count=0, name=key, avatar="")
        user["count"] += 1
        if name.strip():
            user["name"] = name.strip()
        if avatar.strip():
            user["avatar"] = avatar.strip()
        data["poke_users"][key] = user
        await _save(data)


async def record_role(role: str) -> None:
    """按角色名记录一次成功发送。"""
    key = role.strip()
    if not key:
        return
    async with _STATS_LOCK:
        data = await _load()
        data["roles"][key] = (data["roles"][key] if key in data["roles"] else 0) + 1
        await _save(data)


async def get_statistics() -> StatsData:
    """读取统计快照，返回副本供渲染使用。"""
    async with _STATS_LOCK:
        data = await _load()
    return {
        "poke_users": {key: PokeUser(**value) for key, value in data["poke_users"].items()},
        "roles": dict(data["roles"]),
    }
