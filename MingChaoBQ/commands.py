"""鸣潮表情包主命令：随机 / 本地随机 / 检索 / 列表 / 帮助 / 戳一戳 / 索引更新。"""

import re
import json
import time
import random
import asyncio
from pathlib import Path

import aiofiles

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.data_store import get_res_path
from gsuid_core.ai_core.register import ai_tools
from gsuid_core.utils.image.image_tools import change_ev_image_to_bytes

from .api_sync import safe_name, fetch_and_save, download_to_url
from .whitelist import get_group_role, set_group_role, is_group_allowed
from .api_client import ApiPic
from .utils.cache import new_cache_path
from .utils.paths import BQ_ROOT
from .index_generator import load_index, rebuild_index
from .mingchao_config import get_int, get_bool, set_config, get_str_list
from .utils.index_types import Index, PicEntry
from .utils.render_search import render_emotion_list
from .utils.render_overview import render_char_list, render_one_artist, render_artist_overview
from .mingchao_help.get_help import get_help

mcbq_sv = SV("鸣潮表情包", area="ALL", pm=6)
mcbq_admin_sv = SV("鸣潮表情包管理", area="ALL", pm=0)

_WW_ALIAS_FILE = get_res_path() / "XutheringWavesUID" / "alias" / "char_alias.json"


# ==================== 工具函数 ====================


def _with_meta(pic: PicEntry, artist: str, char: str, sub: str) -> PicEntry:
    """给索引里的 pic 补上检索用元信息"""
    entry = PicEntry(file=pic["file"], emotion=pic["emotion"])
    source = pic.get("source")
    if source is not None:
        entry["source"] = source
    entry["_artist"] = artist
    entry["_char"] = char
    entry["_sub"] = sub
    return entry


async def _send_pic(bot: Bot, pic: PicEntry) -> None:
    """发送本地图片。API 来源的只发图, 本地图带【画师】角色 · 表情 标注"""
    full_path = BQ_ROOT / pic["file"]
    if not full_path.exists():
        await bot.send(f"图片文件不存在：{pic['file']}")
        return

    if pic.get("source") == "api" or pic.get("_artist", "") == "API":
        await bot.send(MessageSegment.image(full_path))
        return

    artist = pic.get("_artist", "")
    char = pic.get("_char", "未知角色")
    emotion = pic.get("emotion", "")
    await bot.send([MessageSegment.text(f"【{artist}】{char} · {emotion}"), MessageSegment.image(full_path)])


async def _try_api(role: str = "") -> ApiPic | None:
    """从 API 获取一张，返回 {"url", "name", "role", ...} 或 None"""
    if not get_bool("mcbq_api_enable"):
        return None
    return await fetch_and_save(role=role)


async def _send_from_api(bot: Bot, data: ApiPic) -> None:
    """发送一张 API 来源的图。只发图不带文案，优先用落盘缓存；没存下来就现下载到 cache 再发"""
    saved_path = data.get("saved_path", "")
    if saved_path and Path(saved_path).exists():
        await bot.send(MessageSegment.image(Path(saved_path)))
        return

    temp_path = new_cache_path("api", data["suffix"])
    if await download_to_url(data["url"], temp_path):
        await bot.send(MessageSegment.image(temp_path))
        return

    await bot.send("图片下载失败")


_cached_ww_alias_mtime: float = -1.0
_cached_ww_alias: dict[str, str] = {}

# 鸣潮常见角色拼音首字母缩写映射
_CHAR_PINYIN_MAP: dict[str, str] = {
    "jx": "今汐",
    "cl": "长离",
    "sar": "守岸人",
    "shr": "守岸人",
    "sh": "守岸人",
    "wln": "维里奈",
    "zz": "折枝",
    "xly": "相里要",
    "c": "椿",
    "fll": "弗洛洛",
    "yh": "釉瑚",
    "klt": "柯莱塔",
    "dj": "丹瑾",
    "ak": "安可",
    "cx": "炽霞",
    "bz": "白芷",
    "yw": "渊武",
    "mtf": "莫特斐",
    "tq": "桃祈",
    "kkl": "卡卡罗",
    "jy": "忌炎",
    "yl": "吟霖",
    "pbz": "漂泊者",
    "blt": "布兰特",
    "lkk": "洛可可",
    "zd": "赞迪",
    "fb": "菲比",
    "krl": "坎瑞拉",
}


def _load_ww_alias() -> dict[str, str]:
    """读上游鸣潮插件的角色别名表；带 mtime 内存缓存。"""
    global _cached_ww_alias_mtime, _cached_ww_alias
    if not _WW_ALIAS_FILE.exists():
        _cached_ww_alias_mtime = -1.0
        _cached_ww_alias = {}
        return {}

    try:
        mtime = _WW_ALIAS_FILE.stat().st_mtime
    except OSError:
        return _cached_ww_alias

    if _cached_ww_alias and mtime == _cached_ww_alias_mtime:
        return _cached_ww_alias

    try:
        with open(_WW_ALIAS_FILE, "r", encoding="utf-8") as f:
            raw: object = json.load(f)
    except (OSError, ValueError) as e:
        logger.warning(f"[MingChaoBQ·别名] 读取失败: {e}")
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, str] = {}
    for real_name, aliases in raw.items():
        if not isinstance(real_name, str) or not isinstance(aliases, list):
            continue
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                result[alias.strip()] = real_name
        result.setdefault(real_name, real_name)

    _cached_ww_alias_mtime = mtime
    _cached_ww_alias = result
    return result


def _get_alias_map() -> dict[str, str]:
    result = dict(_load_ww_alias())
    for line in get_str_list("mcbq_char_alias"):
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
    cleaned = keyword.strip()
    if not cleaned:
        return ""
    alias_map = _get_alias_map()
    if cleaned in alias_map:
        return alias_map[cleaned]
    lower = cleaned.lower()
    if lower in alias_map:
        return alias_map[lower]
    if lower in _CHAR_PINYIN_MAP:
        return _CHAR_PINYIN_MAP[lower]
    return cleaned


def _all_char_names(index: Index) -> set[str]:
    names: set[str] = set()
    for chars in index.values():
        names.update(c for c in chars if c != "_default")
    return names


def _match_artists(index: Index, keyword: str) -> list[str]:
    return [name for name in index if name != "API" and (keyword == name or keyword in name or name in keyword)]


def _match_chars(index: Index, keyword: str) -> list[str]:
    real_name = _resolve_char_name(keyword)
    return [real_name] if real_name in _all_char_names(index) else []


def _match_chars_fuzzy(index: Index, keyword: str) -> list[str]:
    """角色名按包含关系兜底("汐" → "今汐")"""
    real_name = _resolve_char_name(keyword)
    names = _all_char_names(index)
    if real_name in names:
        return [real_name]
    return sorted(name for name in names if keyword in name or name in keyword)


def _match_emotions(index: Index, keyword: str, fuzzy: bool = False) -> list[PicEntry]:
    results: list[PicEntry] = []
    for a_name, chars in index.items():
        for c_name, subcats in chars.items():
            for sub_name, pics in subcats.items():
                for pic in pics:
                    emo = pic["emotion"]
                    if emo == keyword or (fuzzy and keyword in emo):
                        results.append(_with_meta(pic, a_name, c_name, sub_name))
    return results


def _search_pics(index: Index, keyword: str) -> tuple[list[PicEntry], str]:
    """
    搜索关键字, 返回 (结果, 列表图上标注的来源)。
    顺序: 表情精确 → 角色(含别名) → 画师 → 表情模糊 → 角色模糊 → 画师模糊。
    表情名取自文件名尾部, 角色名不一定出现在表情名里(「今汐」317 张图里没有一条表情名
    含今汐), 所以必须能按角色/画师兜底; 而精确的角色/画师名要排在"包含关系"的模糊表情名
    之前——否则画师「捏捏」(2263 张)会被 4 个带"捏捏"的表情名截胡。
    """
    exact = _match_emotions(index, keyword, fuzzy=False)
    if exact:
        return exact, ""

    chars = _match_chars(index, keyword)
    char_pics = [pic for name in chars for pic in _collect_all_pics(index, char=name)]
    if char_pics:
        return char_pics, f"角色「{'/'.join(chars[:3])}」"

    if keyword in index and keyword != "API":
        artist_pics = _collect_all_pics(index, artist=keyword)
        if artist_pics:
            return artist_pics, f"画师「{keyword}」"

    fuzzy = _match_emotions(index, keyword, fuzzy=True)
    if fuzzy:
        return fuzzy, "模糊匹配"

    fuzzy_chars = _match_chars_fuzzy(index, keyword)
    fuzzy_char_pics = [pic for name in fuzzy_chars for pic in _collect_all_pics(index, char=name)]
    if fuzzy_char_pics:
        return fuzzy_char_pics, f"角色「{'/'.join(fuzzy_chars[:3])}」"

    artists = _match_artists(index, keyword)
    artist_pics = [pic for name in artists for pic in _collect_all_pics(index, artist=name)]
    if artist_pics:
        return artist_pics, f"画师「{'/'.join(artists[:3])}」"

    return [], ""


def _collect_all_pics(index: Index, artist: str | None = None, char: str | None = None) -> list[PicEntry]:
    """
    从索引里筛选图片，返回带 _artist / _char / _sub 元信息的列表。
    artist 或 char 为空时不筛选该维度。
    """
    results: list[PicEntry] = []
    for a_name, chars in index.items():
        if artist and a_name != artist:
            continue
        for c_name, subcats in chars.items():
            if char and c_name != char:
                continue
            for sub_name, pics in subcats.items():
                results.extend(_with_meta(pic, a_name, c_name, sub_name) for pic in pics)
    return results


def _take_keyword(ev: Event) -> str | None:
    """取命令参数。整句以「列表」结尾时属于列表命令，返回 None 让给它，避免同句回两次。"""
    keyword = ev.text.strip()
    return None if keyword.endswith("列表") else keyword


# ==================== 戳一戳 ====================


@mcbq_sv.on_meta("poke")
async def on_poke(bot: Bot, ev: Event) -> None:
    target_raw: object = ev.get_meta("target_id")
    target_id = str(target_raw) if isinstance(target_raw, (str, int)) else ""
    if target_id != ev.bot_self_id:
        logger.debug(f"[MingChaoBQ·戳一戳] 不是戳我: target={target_id} self={ev.bot_self_id}")
        return

    if not is_group_allowed(ev.group_id):
        return

    if not get_bool("mcbq_poke_enable"):
        return

    role = get_group_role(ev.group_id)
    data = await _try_api(role=role)
    if data is not None:
        await _send_from_api(bot, data)
        return

    index = await load_index()
    pics = _collect_all_pics(index, char=role) if role else []
    if not pics:
        pics = _collect_all_pics(index)
    if not pics:
        logger.info("[MingChaoBQ·戳一戳] 本地索引为空，未发送")
        return
    await _send_pic(bot, random.choice(pics))


# ==================== 用户命令 ====================


@mcbq_sv.on_command(("帮助", "表情包帮助"), to_ai="查看鸣潮表情包插件的帮助图")
async def cmd_help(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return
    await bot.send(MessageSegment.image(await get_help(ev.user_pm)))


@mcbq_sv.on_command("列表", to_ai="查看全部画师与角色的概览图")
async def cmd_all_list(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return
    index = await load_index()
    await bot.send(MessageSegment.image(await render_artist_overview(index, ev.user_pm)))


@mcbq_sv.on_suffix("列表", to_ai="查看某个画师或角色的表情列表图")
async def cmd_sublist(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return

    keyword = ev.text.strip()
    if not keyword:
        await bot.send("请指定画师或角色名，例如：bq捏捏列表")
        return

    index = await load_index()

    matched_chars = _match_chars(index, keyword)
    if matched_chars:
        await bot.send(MessageSegment.image(await render_char_list(index, matched_chars[0], ev.user_pm)))
        return

    matched_artists = _match_artists(index, keyword)
    if matched_artists:
        img = await render_one_artist(index, matched_artists[0], ev.user_pm)
        if img is not None:
            await bot.send(MessageSegment.image(img))
        return

    await bot.send(f"没有找到「{keyword}」相关的画师或角色。发送 bq列表 查看全部。")


@mcbq_sv.on_command("随机表情", to_ai="随机发送一张鸣潮表情包，可跟画师名/角色名/表情名")
async def cmd_random(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return

    keyword = _take_keyword(ev)
    if keyword is None:
        return

    index = await load_index()

    if not keyword:
        data = await _try_api()
        if data is not None:
            await _send_from_api(bot, data)
            return
        pics = _collect_all_pics(index)
        if not pics:
            await bot.send("表情包库是空的，请先运行 bq更新索引。")
            return
        await _send_pic(bot, random.choice(pics))
        return

    matched_chars = _match_chars(index, keyword)
    matched_artists = _match_artists(index, keyword)
    matched_emotions = _match_emotions(index, keyword, fuzzy=False)
    matched_emotions_fuzzy = matched_emotions or _match_emotions(index, keyword, fuzzy=True)

    # 认得出是角色、或本地完全没有对应素材时交给 API（API 关着就自然回退本地）
    if matched_chars or (not matched_artists and not matched_emotions_fuzzy):
        role_param = matched_chars[0] if matched_chars else keyword
        data = await _try_api(role=role_param)
        if data is not None:
            await _send_from_api(bot, data)
            return

    for pics in (
        [pic for c in matched_chars for pic in _collect_all_pics(index, char=c)],
        [pic for a in matched_artists for pic in _collect_all_pics(index, artist=a)],
        matched_emotions,
        matched_emotions_fuzzy,
    ):
        if pics:
            await _send_pic(bot, random.choice(pics))
            return

    await bot.send(f"没有找到「{keyword}」相关的画师、角色或表情。发送 bq列表 查看全部。")


def _parse_burst_args(command: str, raw_text: str) -> tuple[int, str]:
    """解析连发数量（1-5）与查询关键词。"""
    default_count = 3
    if command == "五连":
        default_count = 5
    elif command == "三连":
        default_count = 3

    text = raw_text.strip()
    if not text:
        return default_count, ""

    m_head = re.match(r"^(\d+)\s*张?\s*(.*)$", text)
    if m_head:
        num = int(m_head.group(1))
        kw = m_head.group(2).strip()
        return min(max(num, 1), 5), kw

    m_tail = re.match(r"^(.*?)\s+(\d+)\s*张?$", text)
    if m_tail:
        kw = m_tail.group(1).strip()
        num = int(m_tail.group(2))
        return min(max(num, 1), 5), kw

    return default_count, text


async def _send_burst_items(bot: Bot, items: list[PicEntry | ApiPic]) -> None:
    """连发表情统一发送器：支持合并转发聊天记录与平滑降级。"""
    if not items:
        return

    # 若有多张图且开启了合并转发配置，优先合成聊天记录转发节点
    if len(items) > 1 and get_bool("mcbq_burst_forward"):
        node_elements: list[Message] = []
        for item in items:
            if "file" in item:
                full_path = BQ_ROOT / item["file"]
                if not full_path.exists():
                    continue
                artist = item.get("_artist", "")
                if item.get("source") == "api" or artist == "API":
                    node_elements.append(MessageSegment.image(full_path))
                else:
                    char = item.get("_char", "未知角色")
                    emotion = item.get("emotion", "")
                    node_elements.append(MessageSegment.text(f"【{artist}】{char} · {emotion}"))
                    node_elements.append(MessageSegment.image(full_path))
            else:
                saved_path = item.get("saved_path", "")
                if saved_path and Path(saved_path).exists():
                    node_elements.append(MessageSegment.image(Path(saved_path)))
                else:
                    temp_path = new_cache_path("api", item["suffix"])
                    if await download_to_url(item["url"], temp_path):
                        node_elements.append(MessageSegment.image(temp_path))

        if node_elements:
            try:
                await bot.send(MessageSegment.node(node_elements))
                return
            except Exception as e:
                logger.warning(f"[MingChaoBQ·连发] 合并转发失败，降级为单发: {e}")

    # 降级或未开启合并转发：逐张单发
    for item in items:
        if "file" in item:
            await _send_pic(bot, item)
        else:
            await _send_from_api(bot, item)
        await asyncio.sleep(0.3)


@mcbq_sv.on_command(("连发", "连发表情", "三连", "五连"), to_ai="连发多张鸣潮表情包（1-5张）")
async def cmd_burst(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return

    count, keyword = _parse_burst_args(ev.command, ev.text)
    index = await load_index()

    if not keyword:
        pics = _collect_all_pics(index)
        if not pics:
            data_list: list[ApiPic] = []
            for _ in range(count):
                d = await _try_api()
                if d is not None:
                    data_list.append(d)
            if not data_list:
                await bot.send("表情包库是空的，请先运行 bq更新索引。")
                return
            await _send_burst_items(bot, data_list)
            return

        chosen = random.sample(pics, min(count, len(pics)))
        await _send_burst_items(bot, chosen)
        return

    matched_chars = _match_chars(index, keyword)
    matched_artists = _match_artists(index, keyword)
    matched_emotions = _match_emotions(index, keyword, fuzzy=False)
    matched_emotions_fuzzy = matched_emotions or _match_emotions(index, keyword, fuzzy=True)

    candidates: list[PicEntry] = []
    for p_list in (
        [pic for c in matched_chars for pic in _collect_all_pics(index, char=c)],
        [pic for a in matched_artists for pic in _collect_all_pics(index, artist=a)],
        matched_emotions,
        matched_emotions_fuzzy,
    ):
        if p_list:
            candidates = p_list
            break

    if not candidates:
        fuzzy_chars = _match_chars_fuzzy(index, keyword)
        if fuzzy_chars:
            candidates = [pic for c in fuzzy_chars for pic in _collect_all_pics(index, char=c)]

    if candidates and (len(candidates) >= count or not get_bool("mcbq_api_enable")):
        chosen = random.sample(candidates, min(count, len(candidates)))
        await _send_burst_items(bot, chosen)
        return

    role_param = matched_chars[0] if matched_chars else keyword
    api_results: list[ApiPic] = []
    if get_bool("mcbq_api_enable"):
        for _ in range(count):
            d = await _try_api(role=role_param)
            if d is not None:
                api_results.append(d)

    if api_results:
        await _send_burst_items(bot, api_results)
        return

    if candidates:
        await _send_burst_items(bot, candidates)
        return

    await bot.send(f"没有找到「{keyword}」相关的画师、角色或表情。发送 bq列表 查看全部。")


@mcbq_sv.on_command("本地表情", to_ai="只从本地表情库随机发一张（跳过 API），可跟关键词")
async def cmd_local(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return

    keyword = _take_keyword(ev)
    if keyword is None:
        return

    index = await load_index()

    if not keyword:
        pics = _collect_all_pics(index)
        if not pics:
            await bot.send("本地表情包库是空的，请先运行 bq更新索引。")
            return
        await _send_pic(bot, random.choice(pics))
        return

    matched_chars = _match_chars(index, keyword)
    matched_artists = _match_artists(index, keyword)
    matched_emotions = _match_emotions(index, keyword, fuzzy=False)
    matched_emotions_fuzzy = matched_emotions or _match_emotions(index, keyword, fuzzy=True)

    for pics in (
        [pic for c in matched_chars for pic in _collect_all_pics(index, char=c)],
        [pic for a in matched_artists for pic in _collect_all_pics(index, artist=a)],
        matched_emotions,
        matched_emotions_fuzzy,
    ):
        if pics:
            await _send_pic(bot, random.choice(pics))
            return

    await bot.send(f"本地没有找到「{keyword}」相关的画师、角色或表情。")


@mcbq_sv.on_command("搜索表情", to_ai="按表情名搜索本地表情包并列成一张结果图")
async def cmd_search(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return

    keyword = _take_keyword(ev)
    if keyword is None:
        return
    if not keyword:
        await bot.send("请提供搜索关键词，例如：bq搜索表情 比心")
        return

    index = await load_index()

    matched, note = _search_pics(index, keyword)
    if not matched:
        await bot.send(f"没有找到与「{keyword}」相关的表情、角色或画师。")
        return

    img_path = await render_emotion_list(matched, keyword, note)
    await bot.send(MessageSegment.image(img_path))


@mcbq_sv.on_command("设置戳一戳角色", to_ai="设置本群戳一戳固定发送的角色，需权限")
async def set_poke_role(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return
    if not ev.group_id:
        await bot.send("该命令只能在群聊里使用。")
        return

    min_pm = get_int("mcbq_poke_set_pm", 3)
    if ev.user_pm > min_pm:
        await bot.send(f"权限不足，本命令需要权限等级 ≤ {min_pm}。")
        return

    role = ev.text.strip()
    if not role:
        await bot.send("用法：bq设置戳一戳角色 角色名\n随机：bq设置戳一戳角色 随机")
        return
    if role == "随机":
        set_group_role(ev.group_id, "")
        await bot.send("已恢复本群的戳一戳为随机表情。")
        return

    resolved = _resolve_char_name(role)
    if resolved not in _all_char_names(await load_index()):
        await bot.send(f"本地没有角色「{role}」，请确认角色名是否正确。")
        return
    set_group_role(ev.group_id, resolved)
    await bot.send(f"已设置本群戳一戳表情为「{resolved}」。")


# ==================== 管理命令 ====================


@mcbq_admin_sv.on_command("更新索引", to_ai="重新扫描表情包目录并生成索引（仅主人可用）")
async def update_index(bot: Bot, ev: Event) -> None:
    try:
        index = await rebuild_index()
    except OSError as e:
        await bot.send(f"❌ 索引生成失败：{e}")
        return

    total = sum(len(pics) for chars in index.values() for subcats in chars.values() for pics in subcats.values())
    await bot.send(f"✅ 索引更新完成！共扫描到 {total} 张表情包。")


@mcbq_admin_sv.on_command("开启戳一戳", to_ai="开启戳一戳触发随机表情功能")
async def enable_poke(bot: Bot, ev: Event) -> None:
    set_config("mcbq_poke_enable", True)
    await bot.send("✅ 戳一戳随机表情功能已【开启】。")


@mcbq_admin_sv.on_command("关闭戳一戳", to_ai="关闭戳一戳触发随机表情功能")
async def disable_poke(bot: Bot, ev: Event) -> None:
    set_config("mcbq_poke_enable", False)
    await bot.send("✅ 戳一戳随机表情功能已【关闭】。")


def _detect_image_suffix(data: bytes) -> str:
    """根据文件魔数推断常见图片格式后缀。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


async def _extract_image_bytes(bot: Bot, ev: Event) -> bytes | None:
    """从当前事件或交互等待中提取图片字节。"""
    imgs: list[bytes] = []
    if ev.image:
        b = await change_ev_image_to_bytes(ev.image)
        if isinstance(b, bytes):
            imgs.append(b)
        elif isinstance(b, list):
            imgs.extend(b)
    if not imgs:
        for msg in ev.content:
            if msg.type == "image" and msg.data:
                b = await change_ev_image_to_bytes(msg.data)
                if isinstance(b, bytes):
                    imgs.append(b)
                elif isinstance(b, list):
                    imgs.extend(b)

    if imgs:
        return imgs[0]

    resp = await bot.receive_resp("请发送要添加的表情图片（30秒内有效）：", timeout=30)
    if resp is None:
        return None
    if resp.image:
        b = await change_ev_image_to_bytes(resp.image)
        if isinstance(b, bytes):
            return b
        elif isinstance(b, list) and b:
            return b[0]
    for msg in resp.content:
        if msg.type == "image" and msg.data:
            b = await change_ev_image_to_bytes(msg.data)
            if isinstance(b, bytes):
                return b
            elif isinstance(b, list) and b:
                return b[0]
    return None


def _resolve_add_pic_args(raw_text: str, index: Index) -> tuple[str, str, str]:
    """智能解析上传表情的画师、角色与表情名，无画师时自动归入自定义。"""
    tokens = raw_text.strip().split()
    known_artists = {a for a in index.keys() if a != "API"}
    known_chars = _all_char_names(index)

    if len(tokens) >= 3:
        t0, t1, t2 = tokens[0], tokens[1], " ".join(tokens[2:])
        c0 = _resolve_char_name(t0)
        # 颠倒输入容错：第一项为角色且第二项为已知画师
        if (c0 in known_chars or t0.lower() in _CHAR_PINYIN_MAP) and t1 in known_artists:
            return t1, c0, t2
        return t0, _resolve_char_name(t1), t2

    if len(tokens) == 2:
        t0, t1 = tokens[0], tokens[1]
        c0 = _resolve_char_name(t0)
        c1 = _resolve_char_name(t1)
        is_c0 = c0 in known_chars or t0.lower() in _CHAR_PINYIN_MAP
        is_c1 = c1 in known_chars or t1.lower() in _CHAR_PINYIN_MAP
        is_a0 = t0 in known_artists
        is_a1 = t1 in known_artists

        if is_c0 and not is_a1:
            # 角色 + 表情名（无画师）
            return "自定义", c0, t1
        if is_a0 and not is_c1:
            # 画师 + 表情名（无角色）
            return t0, "综合", t1
        if is_a0 and is_c1:
            # 画师 + 角色（无表情名）
            return t0, c1, f"{c1}_{int(time.time()) % 10000}"
        if not is_a0 and is_c1:
            # 表情名 + 角色
            return "自定义", c1, t0
        return "自定义", c0, t1

    if len(tokens) == 1:
        t0 = tokens[0]
        c0 = _resolve_char_name(t0)
        if c0 in known_chars or t0.lower() in _CHAR_PINYIN_MAP:
            return "自定义", c0, f"{c0}_{int(time.time()) % 10000}"
        if t0 in known_artists:
            return t0, "综合", f"表情_{int(time.time()) % 10000}"
        return "自定义", "综合", t0

    ts = int(time.time()) % 10000
    return "自定义", "综合", f"表情_{ts}"


@mcbq_admin_sv.on_command(
    ("添加表情", "导入表情", "bq添加表情", "bq导入表情", "鸣潮添加表情", "添加鸣潮表情"),
    to_ai="添加表情包到本地表情库（需管理权限）",
)
async def cmd_add_pic(bot: Bot, ev: Event) -> None:
    required_pm = get_int("mcbq_upload_pm", 0)
    if ev.user_pm > required_pm:
        logger.debug(f"[MingChaoBQ·导入] 权限不足: user_pm={ev.user_pm} > required_pm={required_pm}")
        return

    index = await load_index()
    artist, role, emotion = _resolve_add_pic_args(ev.text, index)

    artist_clean = safe_name(artist)
    role_clean = safe_name(role)
    emotion_clean = safe_name(emotion)
    if not artist_clean or not role_clean or not emotion_clean:
        await bot.send("画师、角色或表情名包含非法字符，请重新输入。")
        return

    img_bytes = await _extract_image_bytes(bot, ev)
    if not img_bytes:
        await bot.send("未接收到有效的图片文件，添加取消。")
        return

    ext = _detect_image_suffix(img_bytes)
    save_dir = BQ_ROOT / artist_clean / role_clean
    save_dir.mkdir(parents=True, exist_ok=True)
    target_file = save_dir / f"{emotion_clean}{ext}"

    async with aiofiles.open(target_file, "wb") as f:
        await f.write(img_bytes)

    try:
        await rebuild_index()
    except OSError as e:
        logger.warning(f"[MingChaoBQ·导入] 重建索引异常: {e}")

    await bot.send(f"✅ 成功添加表情包：【{artist_clean}】{role_clean} · {emotion_clean}")


# ==================== AI Core 意图路由工具 ====================


@ai_tools(
    category="common",
    capability_domain="鸣潮表情包",
    covers=["鸣潮表情包", "鸣潮表情", "发鸣潮表情", "鸣潮梗图", "库街区表情"],
    aliases=["鸣潮·发送表情包"],
    brief="发送鸣潮（Wuthering Waves）角色表情包或梗图",
)
async def send_mingchao_meme(
    ev: Event,
    bot: Bot,
    character_or_keyword: str = "",
) -> str:
    """
    发送一张鸣潮（Wuthering Waves）角色的表情包或梗图。

    当用户想要看鸣潮相关表情、梗图或提到特定鸣潮角色（如今汐、长离、守岸人、椿、相里要等）的表情时调用此工具。

    Args:
        ev: 消息事件（框架自动注入）
        bot: 机器人实例（框架自动注入）
        character_or_keyword: 鸣潮角色名、画师名或表情关键词（如"今汐"、"长离"、"比心"、"摸摸头"），可为空。

    Returns:
        发送结果描述
    """
    if not is_group_allowed(ev.group_id):
        return "当前群聊未启用鸣潮表情包功能"

    keyword = character_or_keyword.strip()
    index = await load_index()

    if not keyword:
        data = await _try_api()
        if data is not None:
            await _send_from_api(bot, data)
            return "已发送一张随机鸣潮表情包"
        pics = _collect_all_pics(index)
        if not pics:
            return "表情包库是空的"
        await _send_pic(bot, random.choice(pics))
        return "已发送一张随机鸣潮表情包"

    matched_chars = _match_chars(index, keyword)
    matched_artists = _match_artists(index, keyword)
    matched_emotions = _match_emotions(index, keyword, fuzzy=False)
    matched_emotions_fuzzy = matched_emotions or _match_emotions(index, keyword, fuzzy=True)

    if matched_chars or (not matched_artists and not matched_emotions_fuzzy):
        role_param = matched_chars[0] if matched_chars else keyword
        data = await _try_api(role=role_param)
        if data is not None:
            await _send_from_api(bot, data)
            return f"已发送鸣潮角色「{role_param}」的表情包"

    for pics in (
        [pic for c in matched_chars for pic in _collect_all_pics(index, char=c)],
        [pic for a in matched_artists for pic in _collect_all_pics(index, artist=a)],
        matched_emotions,
        matched_emotions_fuzzy,
    ):
        if pics:
            pic = random.choice(pics)
            await _send_pic(bot, pic)
            return f"已发送鸣潮「{pic.get('emotion', keyword)}」表情包"

    return f"未找到与「{keyword}」相关的鸣潮表情包"
