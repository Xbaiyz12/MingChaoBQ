"""戳一戳资料的兜底来源：meta 事件通常不带 sender 昵称，只能回查 core 用户库。"""

from typing import TypedDict

from sqlmodel import col, select

from gsuid_core.utils.database import base_models
from gsuid_core.utils.database.models import CoreUser

from ..statistics import StatsData

# 用户库里没记到资料时占位写的是 "1"
_PLACEHOLDER = {"", "1"}


class UserProfile(TypedDict):
    name: str
    icon: str


def _clean(value: object, user_id: str) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return "" if text in _PLACEHOLDER or text == user_id else text


async def resolve_profiles(user_ids: list[str], group_id: str | None = None) -> dict[str, UserProfile]:
    """批量取昵称与头像 URL。同一用户有多行（改过群名片）时取最新的，同群记录优先。"""
    keys = [key for key in dict.fromkeys(user_ids) if key]
    if not keys:
        return {}

    # 插件在数据库初始化前就被 import，async_maker 必须走模块属性取最新值
    async with base_models.async_maker() as session:
        result = await session.execute(
            select(CoreUser).where(col(CoreUser.user_id).in_(keys)).order_by(col(CoreUser.id).desc())
        )
        users = result.scalars().all()

    profiles: dict[str, UserProfile] = {}
    group_matched: dict[str, bool] = {}
    for user in users:
        # 已锁定同群资料后，旧行不再有机会覆盖
        if user.user_id in group_matched and group_matched[user.user_id]:
            continue
        name = _clean(user.user_name, user.user_id)
        icon = _clean(user.user_icon, user.user_id)
        if not name and not icon:
            continue
        in_group = group_id is not None and user.group_id == group_id
        old = profiles[user.user_id] if user.user_id in profiles else None
        if old is not None and not in_group:
            continue
        profiles[user.user_id] = UserProfile(
            name=name or (old["name"] if old is not None else ""),
            icon=icon or (old["icon"] if old is not None else ""),
        )
        group_matched[user.user_id] = in_group
    return profiles


async def fill_missing_profiles(data: StatsData) -> None:
    """把统计里只有 QQ 号的用户补上昵称与头像（老数据，或记录时事件没带资料）。"""
    pending = [
        qq for qq, user in data["poke_users"].items() if not user["name"] or user["name"] == qq or not user["avatar"]
    ]
    if not pending:
        return

    profiles = await resolve_profiles(pending)
    for qq in pending:
        profile = profiles[qq] if qq in profiles else None
        if profile is None:
            continue
        user = data["poke_users"][qq]
        if profile["name"] and (not user["name"] or user["name"] == qq):
            user["name"] = profile["name"]
        if profile["icon"] and not user["avatar"]:
            user["avatar"] = profile["icon"]
