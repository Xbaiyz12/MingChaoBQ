import hashlib
import json
import random
from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.data_store import get_res_path
from gsuid_core.models import Event
from gsuid_core.sv import SV
from gsuid_core.segment import MessageSegment

from .utils.paths import BQ_ROOT
from .index_generator import load_index, generate_index, save_index
from .whitelist import is_group_allowed, get_group_role, set_group_role
from .mingchao_config import get_config, set_config
from .api_sync import _get_client, fetch_and_save

mcbq_sv = SV("鸣潮表情包", area="ALL", pm=6)
mcbq_admin_sv = SV("鸣潮表情包管理", area="ALL", pm=0)

_WW_ALIAS_FILE = get_res_path() / "XutheringWavesUID" / "alias" / "char_alias.json"


# ==================== 工具函数 ====================

async def _send_pic(bot: Bot, pic_info: dict):
    """发送本地图片，根据 source 决定标注格式"""
    full_path = BQ_ROOT / pic_info["file"]
    if not full_path.exists():
        await bot.send(f"图片文件不存在：{pic_info['file']}")
        return

    artist = pic_info.get("_artist", "")
    char = pic_info.get("_char", "未知角色")
    emotion = pic_info.get("emotion", "")

    if pic_info.get("source") == "api" or artist == "API":
        label = f"【API】{char}"
    else:
        label = f"【{artist}】{char} · {emotion}"

    await bot.send([
        MessageSegment.text(label),
        MessageSegment.image(full_path),
    ])


async def _try_api(role: str = "") -> dict | None:
    """从 API 获取一张，返回 {"url", "name", "role"} 或 None"""
    if not get_config("mcbq_api_enable"):
        return None
    return await fetch_and_save(role=role)


async def _send_from_api(bot: Bot, data: dict):
    """发送一张 API 来源的图。优先用本地缓存；否则现下载到本地再发"""
    label = f"【API】{data['role']}"

    # 1. 如果 fetch_and_save 已经下载并返回了 saved_path
    saved_path = data.get("saved_path")
    if saved_path and Path(saved_path).exists():
        await bot.send([
            MessageSegment.text(label),
            MessageSegment.image(Path(saved_path)),
        ])
        return

    # 2. 兜底：现下载一次到 cache 目录再发
    import time
    cache_dir = BQ_ROOT / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = data.get("suffix", ".gif")
    temp_path = cache_dir / f"api_{int(time.time() * 1000)}{suffix}"

    client = _get_client()
    ok = await client.download(data["url"], temp_path)
    if ok and temp_path.exists():
        await bot.send([
            MessageSegment.text(label),
            MessageSegment.image(temp_path),
        ])
        return

    await bot.send(label + "\n（图片下载失败）")


def _load_ww_alias() -> dict:
    result = {}
    if not _WW_ALIAS_FILE.exists():
        return result
    try:
        with open(_WW_ALIAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for real_name, aliases in data.items():
            if not isinstance(aliases, list):
                continue
            for alias in aliases:
                alias = str(alias).strip()
                if alias:
                    result[alias] = real_name
            result.setdefault(real_name, real_name)
    except Exception:
        pass
    return result


def _get_alias_map() -> dict:
    result = _load_ww_alias()
    raw = get_config("mcbq_char_alias") or []
    for line in raw:
        if ":" not in line:
            continue
        real, aliases_str = line.split(":", 1)
        real = real.strip()
        if not real:
            continue
        for alias in aliases_str.split(","):
            alias = alias.strip()
            if alias:
                result[alias] = real
    return result


def _resolve_char_name(keyword: str) -> str:
    return _get_alias_map().get(keyword, keyword)


def _match_artists(index: dict, keyword: str) -> list:
    result = []
    for name in index.keys():
        if name == "API":
            continue
        if keyword == name or keyword in name or name in keyword:
            result.append(name)
    return result


def _match_chars(index: dict, keyword: str) -> list:
    real_name = _resolve_char_name(keyword)
    all_chars = set()
    for chars in index.values():
        all_chars.update(c for c in chars.keys() if c != "_default")
    if real_name in all_chars:
        return [real_name]
    return []


def _match_emotions(index: dict, keyword: str, fuzzy: bool = False) -> list:
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


def _collect_all_pics(index: dict, artist: str = None, char: str = None) -> list:
    """
    从索引里筛选图片，返回带 _artist / _char / _sub 元信息的列表。
    artist 或 char 为 None 时不筛选该维度。
    """
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


# ==================== 戳一戳 ====================

@mcbq_sv.on_meta("poke")
async def on_poke(bot: Bot, ev: Event):
    target_id = ev.meta_event_data.get("target_id") if ev.meta_event_data else None
    print(
        f"[MingChaoBQ poke] 收到事件: bot_self_id={ev.bot_self_id}, "
        f"target_id={target_id}, group={ev.group_id}"
    )

    if str(target_id) != str(ev.bot_self_id):
        print(f"[MingChaoBQ poke] 不是戳我（target={target_id} != self={ev.bot_self_id}），退出")
        return

    if not is_group_allowed(ev.group_id):
        print(f"[MingChaoBQ poke] 群 {ev.group_id} 不在白名单或插件总开关关闭，退出")
        return

    if not get_config("mcbq_poke_enable"):
        print("[MingChaoBQ poke] 戳一戳功能未开启，退出")
        return

    if not get_config("mcbq_api_enable"):
        print("[MingChaoBQ poke] API 优先未开启，走本地索引")
    else:
        print("[MingChaoBQ poke] API 优先已开启，尝试从 API 获取")

    group_id = str(ev.group_id)
    role = get_group_role(group_id)
    print(f"[MingChaoBQ poke] group_role={role!r}")
    index = load_index()

    data = await _try_api(role=role or "")
    print(f"[MingChaoBQ poke] API 返回: {data is not None}")

    if data:
        await _send_from_api(bot, data)
        return

    if role:
        pics = _collect_all_pics(index, char=role)
        if pics:
            await _send_pic(bot, random.choice(pics))
            return

    pics = _collect_all_pics(index)
    print(f"[MingChaoBQ poke] 本地索引图片数: {len(pics)}")
    if pics:
        await _send_pic(bot, random.choice(pics))
    else:
        print("[MingChaoBQ poke] 本地索引为空，什么都没发")


# ==================== 主处理 ====================

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

    if text in ("更新索引", "开启白名单", "关闭白名单", "查看白名单"):
        return
    if text.startswith("添加白名单") or text.startswith("移除白名单"):
        return
    if text.startswith("同步api") or text.startswith("设置戳一戳角色"):
        return
    if text in ("开启戳一戳", "关闭戳一戳", "开启定时同步", "关闭定时同步"):
        return

    index = load_index()

    if text == "帮助":
        from .mingchao_help.get_help import get_help
        img = await get_help(ev.user_pm)
        await bot.send(MessageSegment.image(img))
        return

    if text == "列表":
        from .utils.render_overview import render_artist_overview
        img = await render_artist_overview(index, ev.user_pm)
        await bot.send(MessageSegment.image(img))
        return

    if text.startswith("搜索表情 "):
        keyword = text[5:].strip()
        if not keyword:
            await bot.send("请提供搜索关键词，例如：bq搜索表情 比心")
            return

        matched = _match_emotions(index, keyword, fuzzy=False)
        fuzzy = False
        if not matched:
            matched = _match_emotions(index, keyword, fuzzy=True)
            fuzzy = True

        if not matched:
            await bot.send(f"没有找到表情「{keyword}」。换一个词试试吧。")
            return

        from .utils.image_utils import render_text_to_image
        lines = []
        for m in matched:
            artist = m["_artist"]
            char = m["_char"]
            emotion = m["emotion"]
            if m.get("source") == "api" or artist == "API":
                lines.append(f"【API】{char} · {emotion}")
            else:
                lines.append(f"【{artist}】{char} · {emotion}")
        title = f"搜索「{keyword}」共 {len(matched)} 个{'（模糊）' if fuzzy else ''}"
        img_path = render_text_to_image("\n".join(lines), title=title)
        await bot.send(MessageSegment.image(img_path))
        return

    if text == "随机表情":
        data = await _try_api()
        if data:
            await _send_from_api(bot, data)
            return
        pics = _collect_all_pics(index)
        if not pics:
            await bot.send("表情包库是空的，请先运行 bq更新索引。")
            return
        await _send_pic(bot, random.choice(pics))
        return

    if text.startswith("随机表情 "):
        keyword = text[5:].strip()
        if not keyword:
            data = await _try_api()
            if data:
                await _send_from_api(bot, data)
                return
            pics = _collect_all_pics(index)
            if pics:
                await _send_pic(bot, random.choice(pics))
            return

        matched_chars = _match_chars(index, keyword)
        matched_artists = _match_artists(index, keyword)
        matched_emotions = _match_emotions(index, keyword, fuzzy=False)
        matched_emotions_fuzzy = matched_emotions or _match_emotions(index, keyword, fuzzy=True)

        is_role_keyword = bool(matched_chars)

        if is_role_keyword or (not matched_chars and not matched_artists and not matched_emotions_fuzzy):
            data = await _try_api(role=keyword)
            if data:
                await _send_from_api(bot, data)
                return

        if matched_chars:
            pics = []
            for c in matched_chars:
                pics.extend(_collect_all_pics(index, char=c))
            if pics:
                await _send_pic(bot, random.choice(pics))
                return

        if matched_artists:
            pics = []
            for a in matched_artists:
                pics.extend(_collect_all_pics(index, artist=a))
            if pics:
                await _send_pic(bot, random.choice(pics))
                return

        if matched_emotions:
            await _send_pic(bot, random.choice(matched_emotions))
            return

        if matched_emotions_fuzzy:
            await _send_pic(bot, random.choice(matched_emotions_fuzzy))
            return

        await bot.send(f"没有找到「{keyword}」相关的画师、角色或表情。发送 bq列表 查看全部。")
        return

    if text.endswith("列表"):
        keyword = text[:-2].strip()
        if not keyword:
            await bot.send("请指定画师或角色名，例如：bq捏捏列表")
            return

        matched_chars = _match_chars(index, keyword)
        if matched_chars:
            char = matched_chars[0]
            from .utils.render_overview import render_char_list
            img = await render_char_list(index, char, ev.user_pm)
            await bot.send(MessageSegment.image(img))
            return

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

    await bot.send("指令格式有误。发送 bq帮助 查看用法。")


# ==================== 管理命令 ====================

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


@mcbq_admin_sv.on_command("开启戳一戳", to_ai="开启戳一戳触发随机表情功能")
async def enable_poke(bot: Bot, ev: Event):
    set_config("mcbq_poke_enable", True)
    await bot.send("✅ 戳一戳随机表情功能已【开启】。")


@mcbq_admin_sv.on_command("关闭戳一戳", to_ai="关闭戳一戳触发随机表情功能")
async def disable_poke(bot: Bot, ev: Event):
    set_config("mcbq_poke_enable", False)
    await bot.send("✅ 戳一戳随机表情功能已【关闭】。")


@mcbq_admin_sv.on_command("设置戳一戳角色", to_ai="设置本群戳一戳触发的角色（需权限）")
async def set_poke_role(bot: Bot, ev: Event):
    min_pm = int((get_config("mcbq_poke_set_pm") or "3").strip() or 3)
    if ev.user_pm > min_pm:
        await bot.send(f"权限不足，本命令需要权限等级 ≤ {min_pm}。")
        return

    role = ev.text.strip()
    if not role:
        await bot.send("用法：bq设置戳一戳角色 角色名\n随机：bq设置戳一戳角色 随机")
        return
    if role == "随机":
        set_group_role(str(ev.group_id), "")
        await bot.send("已恢复本群的戳一戳为随机表情。")
        return

    resolved = _resolve_char_name(role)
    index = load_index()
    all_chars = set()
    for chars in index.values():
        all_chars.update(c for c in chars.keys() if c != "_default")
    if resolved not in all_chars:
        await bot.send(f"本地没有角色「{role}」，请确认角色名是否正确。")
        return
    set_group_role(str(ev.group_id), resolved)
    await bot.send(f"已设置本群戳一戳表情为「{resolved}」。")


@mcbq_admin_sv.on_command("同步api 数量", to_ai="从 API 随机拉取 N 张到本地（仅主人）")
async def sync_api_cmd(bot: Bot, ev: Event):
    from .api_sync import _get_client, save_api_pic_to_local
    count_str = ev.text.strip()
    try:
        count = int(count_str) if count_str else 50
    except ValueError:
        count = 50
    count = min(count, 500)

    await bot.send(f"开始从 API 拉取 {count} 张，请稍候……")
    client = _get_client()
    success = 0
    skipped = 0
    failed = 0
    seen_urls = set()

    for _ in range(count * 3):
        if success + skipped >= count:
            break
        data = await client.fetch_random_json()
        if not data:
            failed += 1
            continue
        if data["url"] in seen_urls:
            continue
        seen_urls.add(data["url"])

        saved = await save_api_pic_to_local(data)
        if saved:
            success += 1
        else:
            skipped += 1

    index = generate_index()
    save_index(index)
    await bot.send(
        f"✅ 完成！\n新增 {success} 张\n跳过 {skipped} 张\n失败 {failed} 张\n索引已刷新。"
    )