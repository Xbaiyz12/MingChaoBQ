from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .mingchao_config import get_config, set_config

# 白名单管理命令 —— 仅主人可用（pm=0 在 SV 创建时设置）
mcbq_whitelist_sv = SV("鸣潮表情包白名单", area="ALL", pm=0)


def is_group_allowed(group_id) -> bool:
    """检查群是否允许使用本插件。"""
    if not get_config("mcbq_enable"):
        return False
    if not get_config("mcbq_whitelist_enable"):
        return True
    whitelist = get_config("mcbq_whitelist") or []
    return str(group_id) in [str(g) for g in whitelist]


def get_group_role(group_id: str) -> str:
    """读该群的专属戳一戳角色，没有返回空字符串"""
    raw = get_config("mcbq_poke_group_roles") or []
    prefix = f"{group_id}:"
    for line in raw:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def set_group_role(group_id: str, role: str):
    """设置某群的专属角色，role 为空则清除"""
    raw = list(get_config("mcbq_poke_group_roles") or [])
    prefix = f"{group_id}:"
    raw = [l for l in raw if not l.startswith(prefix)]
    if role:
        raw.append(f"{group_id}:{role}")
    set_config("mcbq_poke_group_roles", raw)


@mcbq_whitelist_sv.on_command("开启白名单", to_ai="开启鸣潮表情包插件的群白名单模式")
async def enable_whitelist(bot: Bot, ev: Event):
    set_config("mcbq_whitelist_enable", True)
    await bot.send("鸣潮表情包群白名单已【开启】，只有白名单中的群可以使用本插件。")


@mcbq_whitelist_sv.on_command("关闭白名单", to_ai="关闭鸣潮表情包插件的群白名单模式")
async def disable_whitelist(bot: Bot, ev: Event):
    set_config("mcbq_whitelist_enable", False)
    await bot.send("鸣潮表情包群白名单已【关闭】，所有群均可使用本插件。")


@mcbq_whitelist_sv.on_command("添加白名单", to_ai="添加群号到鸣潮表情包白名单")
async def add_whitelist(bot: Bot, ev: Event):
    group_id = ev.text.strip()
    if not group_id:
        await bot.send("请输入要添加的群号，例如：bq添加白名单 123456789")
        return
    current = get_config("mcbq_whitelist") or []
    if group_id in current:
        await bot.send(f"群 {group_id} 已经在白名单中了。")
        return
    current.append(group_id)
    set_config("mcbq_whitelist", current)
    await bot.send(f"已添加群 {group_id} 到白名单。")


@mcbq_whitelist_sv.on_command("移除白名单", to_ai="从鸣潮表情包白名单中移除群号")
async def remove_whitelist(bot: Bot, ev: Event):
    group_id = ev.text.strip()
    if not group_id:
        await bot.send("请输入要移除的群号，例如：bq移除白名单 123456789")
        return
    current = get_config("mcbq_whitelist") or []
    if group_id not in current:
        await bot.send(f"群 {group_id} 不在白名单中。")
        return
    current.remove(group_id)
    set_config("mcbq_whitelist", current)
    await bot.send(f"已从白名单中移除群 {group_id}。")


@mcbq_whitelist_sv.on_command("查看白名单", to_ai="查看当前鸣潮表情包白名单")
async def list_whitelist(bot: Bot, ev: Event):
    enabled = get_config("mcbq_whitelist_enable")
    current = get_config("mcbq_whitelist") or []
    if not enabled:
        await bot.send("群白名单当前【未启用】，所有群均可使用。")
        return
    if not current:
        await bot.send("群白名单已启用，但列表为空（没有任何群可以使用）。")
        return
    msg = "当前白名单群号：\n" + "\n".join(f"  • {g}" for g in current)
    await bot.send(msg)