import random

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV
from gsuid_core.segment import MessageSegment

from .utils.paths import BQ_ROOT
from .utils.image_utils import render_text_to_image
from .index_generator import load_index, generate_index, save_index
from .whitelist import is_group_allowed
from .mingchao_config import get_config

mcbq_sv = SV("鸣潮表情包", area="ALL", pm=6)
mcbq_admin_sv = SV("鸣潮表情包管理", area="ALL", pm=0)


async def _send_random_pic(bot: Bot, ev: Event, pic_info: dict):
    """发送一张图片，带上画师/角色/表情标注"""
    full_path = BQ_ROOT / pic_info["file"]
    if not full_path.exists():
        await bot.send(f"图片文件不存在：{pic_info['file']}")
        return

    artist = pic_info.get("_artist", "未知画师")
    char = pic_info.get("_char", "未知角色")
    emotion = pic_info.get("emotion", "")

    label = f"【{artist}】{char} · {emotion}"

    await bot.send([
        MessageSegment.text(label),
        MessageSegment.image(full_path),
    ])


def _collect_all_pics(index: dict, artist: str = None, char: str = None) -> list:
    """根据画师/角色筛选所有图片，返回列表。"""
    results = []
    for a_name, chars in index.items():
        if artist and a_name != artist:
            continue
        for c_name, subcats in chars.items():
            if char and c_name != char:
                continue
            for sub_name, pics in subcats.items():
                for pic in pics:
                    results.append({
                        **pic,
                        "_artist": a_name,
                        "_char": c_name,
                        "_sub": sub_name,
                    })
    return results


def _get_alias_map() -> dict:
    """返回 {别名: 真名} 的字典"""
    raw = get_config("mcbq_char_alias") or []
    result = {}
    for line in raw:
        if "=" in line:
            alias, real = line.split("=", 1)
            alias = alias.strip()
            real = real.strip()
            if alias and real:
                result[alias] = real
    return result


def _resolve_char_name(keyword: str) -> str:
    """把别名转换成真名，如果不是别名则原样返回"""
    alias_map = _get_alias_map()
    return alias_map.get(keyword, keyword)


def _match_artists(index: dict, keyword: str) -> list:
    """模糊匹配画师名"""
    result = []
    for name in index.keys():
        if keyword == name or keyword in name or name in keyword:
            result.append(name)
    return result


def _match_chars(index: dict, keyword: str) -> list:
    """
    匹配角色名（仅精确匹配，含别名）。
    不再做模糊匹配，避免"爱心"里包含"心"从而误命中角色"心"。
    """
    real_name = _resolve_char_name(keyword)
    all_chars = set()
    for chars in index.values():
        all_chars.update(c for c in chars.keys() if c != "_default")

    if real_name in all_chars:
        return [real_name]
    return []


def _match_emotions(index: dict, keyword: str, fuzzy: bool = False) -> list:
    """
    匹配表情名。
    fuzzy=False：精确匹配（emotion == keyword）
    fuzzy=True：包含匹配（keyword in emotion）
    """
    results = []
    for a_name, chars in index.items():
        for c_name, subcats in chars.items():
            for sub_name, pics in subcats.items():
                for pic in pics:
                    emo = pic["emotion"]
                    if emo == keyword or (fuzzy and keyword in emo):
                        results.append({
                            **pic,
                            "_artist": a_name,
                            "_char": c_name,
                            "_sub": sub_name,
                        })
    return results


@mcbq_sv.on_regex(
    r"^(?P<text>.+)$",
    to_ai="鸣潮表情包指令。支持 bq随机表情 [画师/角色/表情]、bq搜索表情、bqXX列表、bq列表、bq帮助。",
)
async def general_handler(bot: Bot, ev: Event):
    if not is_group_allowed(ev.group_id):
        return
    text = ev.regex_dict.get("text", "").strip()
    if not text:
        return

    # 管理命令由其他 SV 处理，这里直接跳过，避免"指令格式有误"
    if text in ("更新索引", "开启白名单", "关闭白名单", "查看白名单"):
        return
    if text.startswith("添加白名单") or text.startswith("移除白名单"):
        return
    if text.startswith("同步api") or text in ("开启定时同步", "关闭定时同步"):
        return

    index = load_index()

    # ==================== 帮助 ====================
    if text == "帮助":
        from .mingchao_help.get_help import get_help
        img = await get_help(ev.user_pm)
        await bot.send(MessageSegment.image(img))
        return

    # ==================== 全部列表 ====================
    if text == "列表":
        from .utils.render_overview import render_artist_overview
        img = await render_artist_overview(index, ev.user_pm)
        await bot.send(MessageSegment.image(img))
        return

    # ==================== 搜索表情（只搜表情名） ====================
    if text.startswith("搜索表情 "):
        keyword = text[5:].strip()
        if not keyword:
            await bot.send("请提供搜索关键词，例如：bq搜索表情 比心")
            return

        # 先精确，再模糊
        matched = _match_emotions(index, keyword, fuzzy=False)
        if not matched:
            matched = _match_emotions(index, keyword, fuzzy=True)

        if not matched:
            await bot.send(f"没有找到表情「{keyword}」。换一个词试试吧。")
            return

        await _send_random_pic(bot, ev, random.choice(matched))
        return

    # ==================== 随机表情 [关键词] ====================
    if text == "随机表情":
        pics = _collect_all_pics(index)
        if not pics:
            await bot.send("表情包库是空的，请先运行 bq更新索引。")
            return
        await _send_random_pic(bot, ev, random.choice(pics))
        return

    if text.startswith("随机表情 "):
        keyword = text[5:].strip()
        if not keyword:
            pics = _collect_all_pics(index)
            if not pics:
                await bot.send("表情包库是空的。")
                return
            await _send_random_pic(bot, ev, random.choice(pics))
            return

        # 优先级：角色精确 > 画师模糊 > 表情精确 > 表情模糊

        # 1. 角色精确匹配
        matched_chars = _match_chars(index, keyword)
        if matched_chars:
            pics = []
            for c in matched_chars:
                pics.extend(_collect_all_pics(index, char=c))
            if pics:
                await _send_random_pic(bot, ev, random.choice(pics))
                return

        # 2. 画师模糊匹配
        matched_artists = _match_artists(index, keyword)
        if matched_artists:
            pics = []
            for a in matched_artists:
                pics.extend(_collect_all_pics(index, artist=a))
            if pics:
                await _send_random_pic(bot, ev, random.choice(pics))
                return

        # 3. 表情精确匹配
        matched_emotions = _match_emotions(index, keyword, fuzzy=False)
        if matched_emotions:
            await _send_random_pic(bot, ev, random.choice(matched_emotions))
            return

        # 4. 表情模糊匹配
        matched_emotions = _match_emotions(index, keyword, fuzzy=True)
        if matched_emotions:
            await _send_random_pic(bot, ev, random.choice(matched_emotions))
            return

        await bot.send(f"没有找到「{keyword}」相关的画师、角色或表情。发送 bq列表 查看全部。")
        return

    # ==================== XX列表 ====================
    if text.endswith("列表"):
        keyword = text[:-2].strip()
        if not keyword:
            await bot.send("请指定画师或角色名，例如：bq捏捏列表")
            return

        # 优先匹配角色
        matched_chars = _match_chars(index, keyword)
        if matched_chars:
            char = matched_chars[0]
            from .utils.render_overview import render_char_list
            img = await render_char_list(index, char, ev.user_pm)
            await bot.send(MessageSegment.image(img))
            return

        # 再匹配画师
        matched_artists = _match_artists(index, keyword)
        if matched_artists:
            artist = matched_artists[0]
            from .utils.render_overview import render_one_artist
            img = await render_one_artist(index, artist, ev.user_pm)
            if img is not None:
                await bot.send(MessageSegment.image(img))
            return

        await bot.send(f"没有找到「{keyword}」相关的画师或角色。发送 bq列表 查看全部。")
        return

    # ==================== 兜底 ====================
    await bot.send("指令格式有误。发送 bq帮助 查看用法。")


# ==================== 管理命令（仅主人） ====================

@mcbq_admin_sv.on_command("更新索引", to_ai="重新扫描表情包目录并生成索引（仅主人可用）")
async def update_index(bot: Bot, ev: Event):
    try:
        index = generate_index()
        save_index(index)
        total = sum(
            len(pics)
            for chars in index.values()
            for subcats in chars.values()
            for pics in subcats.values()
        )
        await bot.send(f"✅ 索引更新完成！共扫描到 {total} 张表情包。")
    except Exception as e:
        await bot.send(f"❌ 索引生成失败：{e}")


@mcbq_admin_sv.on_command("同步api", to_ai="从 API 拉取表情包到本地（仅主人）")
async def sync_api_cmd(bot: Bot, ev: Event):
    from .api_sync import sync_from_api
    from .index_generator import generate_index, save_index

    await bot.send("开始同步，请稍候……")
    try:
        stats = await sync_from_api()
        index = generate_index()
        save_index(index)
        await bot.send(
            f"✅ 同步完成！\n"
            f"API 返回 {stats['total']} 个\n"
            f"新增 {stats['success']} 个\n"
            f"跳过（已存在） {stats['skipped']} 个\n"
            f"失败 {stats['failed']} 个\n"
            f"索引已刷新。"
        )
    except Exception as e:
        await bot.send(f"❌ 同步失败：{e}")


@mcbq_admin_sv.on_command("开启定时同步", to_ai="按配置每天自动同步 API（仅主人）")
async def enable_auto_sync(bot: Bot, ev: Event):
    from gsuid_core.scheduler import scheduler
    from .api_sync import sync_from_api
    from .index_generator import generate_index, save_index
    from .mingchao_config import get_config

    hour = int((get_config("mcbq_api_sync_hour") or "4").strip() or 4)

    async def job():
        try:
            await sync_from_api()
            index = generate_index()
            save_index(index)
        except Exception:
            pass

    scheduler.add_job(
        job,
        "cron",
        hour=hour,
        minute=0,
        id="mcbq_api_sync",
        replace_existing=True,
    )
    await bot.send(f"✅ 已开启定时同步，每天 {hour}:00 自动执行一次。")


@mcbq_admin_sv.on_command("关闭定时同步", to_ai="关闭定时同步（仅主人）")
async def disable_auto_sync(bot: Bot, ev: Event):
    from gsuid_core.scheduler import scheduler
    try:
        scheduler.remove_job("mcbq_api_sync")
        await bot.send("✅ 已关闭定时同步。")
    except Exception:
        await bot.send("定时同步任务当前未启用。")