"""群白名单 / 黑名单判定与管理命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .mingchao_config import get_bool, set_config, get_str_list

mcbq_whitelist_sv = SV("鸣潮表情包白名单", area="ALL", pm=0)


def is_group_allowed(group_id: str | None) -> bool:
    """
    检查群是否允许使用本插件。
    优先级：总开关 > 黑名单 > 白名单。
    私聊没有群号，黑白名单只针对群，因此只受总开关约束。
    """
    if not get_bool("mcbq_enable"):
        return False

    if not group_id:
        return True

    group_id_str = str(group_id)

    # 黑名单：无论在不在白名单都禁
    if group_id_str in get_str_list("mcbq_blacklist"):
        return False

    # 白名单未启用：全部放行
    if not get_bool("mcbq_whitelist_enable"):
        return True

    # 白名单匹配
    return group_id_str in get_str_list("mcbq_whitelist")


def get_group_role(group_id: str | None) -> str:
    """取本群固定的戳一戳角色，未设置返回空串。"""
    if not group_id:
        return ""
    raw = get_str_list("mcbq_poke_group_roles")
    prefix = f"{group_id}:"
    for line in raw:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def set_group_role(group_id: str | None, role: str) -> None:
    """设置/清除本群固定戳一戳角色。私聊没有群号，直接忽略。"""
    if not group_id:
        return
    raw = get_str_list("mcbq_poke_group_roles")
    prefix = f"{group_id}:"
    kept = [line for line in raw if not line.startswith(prefix)]
    if role:
        kept.append(f"{group_id}:{role}")
    set_config("mcbq_poke_group_roles", kept)


# ==================== 白名单 ====================


@mcbq_whitelist_sv.on_command("开启白名单", to_ai="开启鸣潮表情包插件的群白名单模式")
async def enable_whitelist(bot: Bot, ev: Event) -> None:
    set_config("mcbq_whitelist_enable", True)
    await bot.send("鸣潮表情包群白名单已【开启】，只有白名单中的群可以使用本插件。")


@mcbq_whitelist_sv.on_command("关闭白名单", to_ai="关闭鸣潮表情包插件的群白名单模式")
async def disable_whitelist(bot: Bot, ev: Event) -> None:
    set_config("mcbq_whitelist_enable", False)
    await bot.send("鸣潮表情包群白名单已【关闭】，所有群均可使用本插件（黑名单除外）。")


@mcbq_whitelist_sv.on_command("添加白名单", to_ai="添加群号到鸣潮表情包白名单")
async def add_whitelist(bot: Bot, ev: Event) -> None:
    group_id = ev.text.strip()
    if not group_id:
        await bot.send("请输入要添加的群号，例如：bq添加白名单 123456789")
        return
    current = get_str_list("mcbq_whitelist")
    if group_id in current:
        await bot.send(f"群 {group_id} 已经在白名单中了。")
        return
    current.append(group_id)
    set_config("mcbq_whitelist", current)
    await bot.send(f"已添加群 {group_id} 到白名单。")


@mcbq_whitelist_sv.on_command("移除白名单", to_ai="从鸣潮表情包白名单中移除群号")
async def remove_whitelist(bot: Bot, ev: Event) -> None:
    group_id = ev.text.strip()
    if not group_id:
        await bot.send("请输入要移除的群号，例如：bq移除白名单 123456789")
        return
    current = get_str_list("mcbq_whitelist")
    if group_id not in current:
        await bot.send(f"群 {group_id} 不在白名单中。")
        return
    current.remove(group_id)
    set_config("mcbq_whitelist", current)
    await bot.send(f"已从白名单中移除群 {group_id}。")


@mcbq_whitelist_sv.on_command("查看白名单", to_ai="查看当前鸣潮表情包白名单")
async def list_whitelist(bot: Bot, ev: Event) -> None:
    enabled = get_bool("mcbq_whitelist_enable")
    current = get_str_list("mcbq_whitelist")
    if not enabled:
        await bot.send("群白名单当前【未启用】，所有群均可使用（黑名单除外）。")
        return
    if not current:
        await bot.send("群白名单已启用，但列表为空（没有任何群可以使用）。")
        return
    msg = "当前白名单群号：\n" + "\n".join(f"  • {g}" for g in current)
    await bot.send(msg)


# ==================== 黑名单 ====================


@mcbq_whitelist_sv.on_command("添加黑名单", to_ai="添加群号到鸣潮表情包黑名单")
async def add_blacklist(bot: Bot, ev: Event) -> None:
    group_id = ev.text.strip()
    if not group_id:
        await bot.send("请输入要添加的群号，例如：bq添加黑名单 123456789")
        return
    current = get_str_list("mcbq_blacklist")
    if group_id in current:
        await bot.send(f"群 {group_id} 已经在黑名单中了。")
        return
    current.append(group_id)
    set_config("mcbq_blacklist", current)
    await bot.send(f"已添加群 {group_id} 到黑名单，该群将无法使用本插件。")


@mcbq_whitelist_sv.on_command("移除黑名单", to_ai="从鸣潮表情包黑名单中移除群号")
async def remove_blacklist(bot: Bot, ev: Event) -> None:
    group_id = ev.text.strip()
    if not group_id:
        await bot.send("请输入要移除的群号，例如：bq移除黑名单 123456789")
        return
    current = get_str_list("mcbq_blacklist")
    if group_id not in current:
        await bot.send(f"群 {group_id} 不在黑名单中。")
        return
    current.remove(group_id)
    set_config("mcbq_blacklist", current)
    await bot.send(f"已从黑名单中移除群 {group_id}。")


@mcbq_whitelist_sv.on_command("查看黑名单", to_ai="查看当前鸣潮表情包黑名单")
async def list_blacklist(bot: Bot, ev: Event) -> None:
    current = get_str_list("mcbq_blacklist")
    if not current:
        await bot.send("黑名单为空，没有任何群被禁用。")
        return
    msg = "当前黑名单群号：\n" + "\n".join(f"  • {g}" for g in current)
    await bot.send(msg)
