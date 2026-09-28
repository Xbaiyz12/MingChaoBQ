"""MingChaoBQ 的戳一戳与表情名统计。"""

import json
import asyncio
from typing import TypedDict

import aiofiles

from .utils.paths import BQ_ROOT

_STATS_PATH = BQ_ROOT / "statistics.json"
_STATS_LOCK = asyncio.Lock()


class _StatsData(TypedDict):
    poke_users: dict[str, int]
    emotions: dict[str, int]


def _empty_stats() -> _StatsData:
    return {"poke_users": {}, "emotions": {}}


def _read_stats(raw: object) -> _StatsData:
    if not isinstance(raw, dict):
        return _empty_stats()
    poke_raw = raw["poke_users"] if "poke_users" in raw else {}
    emotion_raw = raw["emotions"] if "emotions" in raw else {}
    poke_users = (
        {key: value for key, value in poke_raw.items() if isinstance(key, str) and isinstance(value, int)}
        if isinstance(poke_raw, dict)
        else {}
    )
    emotions = (
        {key: value for key, value in emotion_raw.items() if isinstance(key, str) and isinstance(value, int)}
        if isinstance(emotion_raw, dict)
        else {}
    )
    return {"poke_users": poke_users, "emotions": emotions}


async def _load() -> _StatsData:
    if not _STATS_PATH.exists():
        return _empty_stats()
    async with aiofiles.open(_STATS_PATH, encoding="utf-8") as file:
        content = await file.read()
    if not content.strip():
        return _empty_stats()
    return _read_stats(json.loads(content))


async def _save(data: _StatsData) -> None:
    _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _STATS_PATH.with_suffix(".tmp")
    async with aiofiles.open(temp_path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(data, ensure_ascii=False, indent=2))
    temp_path.replace(_STATS_PATH)


async def record_poke(user_id: str) -> None:
    """记录一次有效的戳一戳互动。"""
    key = user_id.strip() or "未知用户"
    async with _STATS_LOCK:
        data = await _load()
        data["poke_users"][key] = data["poke_users"].get(key, 0) + 1
        await _save(data)


async def record_emotion(emotion: str) -> None:
    """只按表情名记录一次发送，不保存画师与角色。"""
    key = emotion.strip()
    if not key:
        return
    async with _STATS_LOCK:
        data = await _load()
        data["emotions"][key] = data["emotions"].get(key, 0) + 1
        await _save(data)


async def get_statistics() -> _StatsData:
    """读取统计快照，返回副本供渲染使用。"""
    async with _STATS_LOCK:
        data = await _load()
    return {"poke_users": dict(data["poke_users"]), "emotions": dict(data["emotions"])}
