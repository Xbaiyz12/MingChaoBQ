"""鸣潮表情包主命令：随机 / 本地随机 / 检索 / 列表 / 帮助 / 戳一戳 / 索引更新。"""

import re
import json
import time
import random
import asyncio
from typing import TypedDict
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
from .statistics import record_poke, record_role, get_statistics
from .utils.cache import new_cache_path
from .utils.paths import BQ_ROOT
from .index_generator import count_pics, load_index, rebuild_index
from .mingchao_config import get_int, get_bool, set_config, get_str_list
from .utils.user_names import resolve_profiles, fill_missing_profiles
from .utils.index_types import Index, PicEntry
from .utils.render_search import MAX_LIST_ITEMS, render_emotion_list
from .utils.render_overview import render_char_list, render_one_artist, render_artist_overview
from .mingchao_help.get_help import get_help
from .utils.render_statistics import render_poke_statistics, render_role_statistics

mcbq_sv = SV("鸣潮表情包", area="ALL", pm=6)
mcbq_admin_sv = SV("鸣潮表情包管理", area="ALL", pm=0)

# 上传时缺层的兜底目录名
_DEFAULT_ARTIST = "自定义"
_DEFAULT_ROLE = "综合"

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


def _char_of(pic: PicEntry) -> str:
    """取统计用的角色名：画师目录下直接放的图没有角色目录，归为未分类。"""
    char = pic.get("_char", "")
    return "未分类" if char in ("", "_default") else char


async def _poker_profile(ev: Event) -> tuple[str, str]:
    """戳一戳的昵称与头像。meta 事件基本不带 sender 资料，缺什么就用用户库里的补。"""
    name = ""
    if "nickname" in ev.sender and isinstance(ev.sender["nickname"], str):
        name = ev.sender["nickname"].strip()
    avatar = ""
    if "avatar" in ev.sender and isinstance(ev.sender["avatar"], str):
        avatar = ev.sender["avatar"].strip()

    if not name or not avatar:
        profiles = await resolve_profiles([ev.user_id], ev.group_id)
        profile = profiles[ev.user_id] if ev.user_id in profiles else None
        if profile is not None:
            name = name or profile["name"]
            avatar = avatar or profile["icon"]
    return name or ev.user_id, avatar


async def _send_pic(bot: Bot, pic: PicEntry) -> None:
    """发送本地图片。API 来源的只发图, 本地图带【画师】角色 · 表情 标注"""
    full_path = BQ_ROOT / pic["file"]
    if not full_path.exists():
        await bot.send(f"图片文件不存在：{pic['file']}")
        return

    if pic.get("source") == "api" or pic.get("_artist", "") == "API":
        await bot.send(MessageSegment.image(full_path))
        await record_role(_char_of(pic))
        return

    artist = pic.get("_artist", "")
    char = pic.get("_char", "未知角色")
    emotion = pic.get("emotion", "")
    await bot.send([MessageSegment.text(f"【{artist}】{char} · {emotion}"), MessageSegment.image(full_path)])
    await record_role(_char_of(pic))


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
        await record_role(data["role"])
        return

    temp_path = new_cache_path("api", data["suffix"])
    if await download_to_url(data["url"], temp_path):
        await bot.send(MessageSegment.image(temp_path))
        await record_role(data["role"])
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

    sender_name, sender_avatar = await _poker_profile(ev)
    # 被戳次数与「是否自动回图」无关，关掉自动回图的群也要照常统计
    await record_poke(ev.user_id, sender_name, sender_avatar)

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


@mcbq_sv.on_command("戳一戳统计", to_ai="查看戳一戳统计图")
async def cmd_poke_statistics(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return
    # 榜上有成员 QQ 号，只允许在群里看，避免私聊把别的群成员晒出来
    if not ev.group_id:
        await bot.send("该命令只能在群聊中使用。")
        return
    data = await get_statistics()
    await fill_missing_profiles(data)
    await bot.send(MessageSegment.image(await render_poke_statistics(data)))


@mcbq_sv.on_command(("表情统计", "表情发送统计"), to_ai="查看角色名发送统计图")
async def cmd_role_statistics(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return
    await bot.send(MessageSegment.image(await render_role_statistics(await get_statistics())))


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


def _parse_emotion_choice(text: str, total: int) -> int | None:
    """解析「表情3」「3」「第3个」这类选择，返回 0 起的下标；无效返回 None。"""
    match = re.search(r"\d+", text)
    if match is None:
        return None
    value = int(match.group())
    return value - 1 if 1 <= value <= total else None


# 画师名下列表时，每个角色最多展示几个
_PER_CHAR_LIMIT = 10


def _sample_by_char(pics: list[PicEntry], per_char: int, limit: int) -> list[PicEntry]:
    """按角色轮流抽，单个角色最多 per_char 张，总数不超过 limit。

    画师动辄上千张（捏捏 2263 张），顺序取前 N 张会被同一个角色占满；
    轮流取才能让画师名下的每个角色都露个脸。
    """
    buckets: dict[str, list[PicEntry]] = {}
    for pic in pics:
        buckets.setdefault(_char_of(pic), []).append(pic)

    picked: list[PicEntry] = []
    for round_index in range(per_char):
        for bucket in buckets.values():
            if round_index >= len(bucket):
                continue
            picked.append(bucket[round_index])
            if len(picked) >= limit:
                return picked
    return picked


def _pick_candidates(pics: list[PicEntry], note: str) -> tuple[list[PicEntry], str]:
    """候选列表的取法：画师名下按角色轮流取（每角色上限 10），其余顺序取前 50。"""
    if not note.startswith("画师"):
        return pics[:MAX_LIST_ITEMS], note
    sampled = _sample_by_char(pics, _PER_CHAR_LIMIT, MAX_LIST_ITEMS)
    return sampled, f"{note} · 每个角色最多 {_PER_CHAR_LIMIT} 个"


async def _send_with_picker(bot: Bot, pics: list[PicEntry], keyword: str, note: str = "") -> bool:
    """命中多张时先出缩略图候选让用户挑，再发选中的那张；只有一张就直接发。

    返回 True 表示这条命令已经处理完，调用方不该再往下走。
    """
    if not pics:
        return False
    if len(pics) == 1:
        await _send_pic(bot, pics[0])
        return True

    candidates, sampled_note = _pick_candidates(pics, note)
    await bot.send(
        MessageSegment.image(
            await render_emotion_list(
                candidates,
                keyword,
                sampled_note,
                hint="回复「表情N」发送第 N 个",
                total=len(pics),
            )
        )
    )
    resp = await bot.receive_resp("请回复要发送的表情编号，例如：表情1", timeout=30)
    if resp is None:
        return True
    picked = _parse_emotion_choice(resp.text, len(candidates))
    if picked is None:
        await bot.send(f"没看懂「{resp.text.strip() or '空消息'}」，请回复 表情1 ~ 表情{len(candidates)}。")
        return True
    await _send_pic(bot, candidates[picked])
    return True


@mcbq_sv.on_command("随机表情", to_ai="随机发送一张鸣潮表情包，可跟画师名/角色名/表情名")
async def cmd_random(bot: Bot, ev: Event) -> None:
    if not is_group_allowed(ev.group_id):
        return

    keyword = _take_keyword(ev)
    if keyword is None:
        return

    index = await load_index()

    if not keyword:
        # 不带关键词时才问 API：有关键词要出候选列表，交给 API 就看不到清单了
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

    matched, note = _search_pics(index, keyword)
    if not matched:
        await bot.send(f"没有找到「{keyword}」相关的画师、角色或表情。发送 bq列表 查看全部。")
        return
    await _send_with_picker(bot, matched, keyword, note)


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
        node_roles: list[str] = []
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
                node_roles.append(_char_of(item))
            else:
                saved_path = item.get("saved_path", "")
                if saved_path and Path(saved_path).exists():
                    node_elements.append(MessageSegment.image(Path(saved_path)))
                    node_roles.append(item["role"])
                else:
                    temp_path = new_cache_path("api", item["suffix"])
                    if await download_to_url(item["url"], temp_path):
                        node_elements.append(MessageSegment.image(temp_path))
                        node_roles.append(item["role"])

        if node_elements:
            try:
                await bot.send(MessageSegment.node(node_elements))
                for role in node_roles:
                    await record_role(role)
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

    matched, note = _search_pics(index, keyword)
    if not matched:
        await bot.send(f"本地没有找到「{keyword}」相关的画师、角色或表情。")
        return
    await _send_with_picker(bot, matched, keyword, note)


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

    total = count_pics(index)
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


def _unique_stem(directory: Path, stem: str, ext: str) -> str:
    """同名文件已存在时补序号，避免自动生成的名字把上一张悄悄覆盖掉。"""
    if not (directory / f"{stem}{ext}").exists():
        return stem
    seq = 2
    while (directory / f"{stem}_{seq}{ext}").exists():
        seq += 1
    return f"{stem}_{seq}"


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


def _norm_name(name: str) -> str:
    """压掉所有空白并统一大小写，用来跟本地已有目录名比对。"""
    return re.sub(r"\s+", "", name).casefold()


def _lookup_local(name: str, candidates: list[str]) -> tuple[str, list[str]]:
    """在本地名字里找 name：先精确（忽略大小写与空格），再模糊包含。

    返回 (唯一确定的本地名, 待用户选择的候选)；两者互斥，已确定时候选为空。
    """
    target = _norm_name(name)
    if not target:
        return "", []
    exact = [item for item in candidates if _norm_name(item) == target]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return "", exact
    fuzzy = [item for item in candidates if target in _norm_name(item) or _norm_name(item) in target]
    if len(fuzzy) == 1:
        return fuzzy[0], []
    return "", fuzzy


class AddPicPlan(TypedDict):
    artist: str
    role: str
    emotion: str
    artist_choices: list[str]
    role_choices: list[str]
    artist_local: bool
    role_local: bool


# 显式标注写法：画师:名字 / 角色:名字 / 表情:名字（中英文都认）
_LABEL_ALIASES = {
    "画师": "artist",
    "作者": "artist",
    "artist": "artist",
    "角色": "role",
    "char": "role",
    "role": "role",
    "表情": "emotion",
    "表情名": "emotion",
    "emotion": "emotion",
}
_LABEL_RE = re.compile(
    r"(?:^|\s)(画师|作者|角色|char|role|表情名|表情|artist|emotion)[:：]\s*"
    r"(.*?)(?=\s*(?:画师|作者|角色|char|role|表情名|表情|artist|emotion)[:：]|$)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_labeled_tokens(raw_text: str) -> tuple[str, str, str] | None:
    """解析「画师:X」这类显式标注；一个标注都没有时返回 None 走自动分层。

    按整串扫而不是按空格切词：画师名本身可能带空格（如 MIX CRAFT）。
    """
    found: dict[str, list[str]] = {"artist": [], "role": [], "emotion": []}
    matched = False
    for match in _LABEL_RE.finditer(raw_text):
        matched = True
        value = match.group(2).strip()
        if value:
            found[_LABEL_ALIASES[match.group(1).lower()]].append(value)
    if not matched:
        return None
    return " ".join(found["artist"]), " ".join(found["role"]), " ".join(found["emotion"])


def _strip_prefix(text: str, name: str) -> str | None:
    """text 是否以 name 开头（忽略空白与大小写差异）？是则返回剩余文本。"""
    cursor = 0
    for char in name:
        if char.isspace():
            continue
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor].casefold() != char.casefold():
            return None
        cursor += 1
    return text[cursor:].strip()


def _split_known_prefix(text: str, artists: list[str], chars: list[str]) -> tuple[str, str, str] | None:
    """按本地已知名字切前缀。名字可能含空格（MIX CRAFT），所以长的先试。"""
    for name in sorted(artists, key=len, reverse=True):
        rest = _strip_prefix(text, name)
        if rest is None:
            continue
        if not rest:
            return name, "", ""
        for char in sorted(chars, key=len, reverse=True):
            rest2 = _strip_prefix(rest, char)
            if rest2 is not None:
                return name, char, rest2
        return name, "", rest
    for name in sorted(chars, key=len, reverse=True):
        rest = _strip_prefix(text, name)
        if rest is None:
            continue
        if not rest:
            return "", name, ""
        # 角色写在前面也要能归位：角色 + 画师 + 表情
        for artist in sorted(artists, key=len, reverse=True):
            rest2 = _strip_prefix(rest, artist)
            if rest2 is not None:
                return artist, name, rest2
        return "", name, rest
    return None


def _local_names(index: Index) -> tuple[list[str], list[str]]:
    """本地已有的画师名与角色名（都不含 API 目录与 _default 占位）。"""
    artists = sorted(name for name in index if name != "API")
    chars = sorted(_all_char_names(index))
    return artists, chars


def _plan_add_pic(raw_text: str, index: Index) -> AddPicPlan:
    """把上传参数拆成画师 / 角色 / 表情名三层，缺哪层就留空（空层不建目录）。

    三种写法，优先级从高到低：
    - 显式标注 `画师:捏捏 角色:今汐 表情:比心`：想用本地还没有的画师名时用它，无歧义；
    - 本地已知名字前缀匹配（名字可含空格）：`MIX CRAFT 比心` / `今汐 摸摸头`；
    - 纯参数自动分层兜底：识别不出的词一律当表情名，绝不乱建画师目录。
    画师优先落到本地已有目录（先精确，再忽略大小写/空格，最后模糊包含）。
    """
    artists, chars = _local_names(index)
    tokens = raw_text.strip().split()

    def looks_artist(token: str) -> bool:
        hit, choices = _lookup_local(token, artists)
        return bool(hit or choices)

    def looks_char(token: str) -> bool:
        resolved = _resolve_char_name(token)
        if resolved in chars or token.lower() in _CHAR_PINYIN_MAP:
            return True
        hit, choices = _lookup_local(resolved, chars)
        return bool(hit or choices)

    def build(artist: str, role: str, emotion: str) -> AddPicPlan:
        resolved_role = _resolve_char_name(role) if role else ""
        artist_hit, artist_choices = _lookup_local(artist, artists) if artist else ("", [])
        role_hit, role_choices = _lookup_local(resolved_role, chars) if resolved_role else ("", [])
        return AddPicPlan(
            artist=artist_hit or artist,
            role=role_hit or resolved_role,
            emotion=emotion,
            artist_choices=artist_choices,
            role_choices=role_choices,
            artist_local=bool(artist_hit),
            role_local=bool(role_hit),
        )

    labeled = _parse_labeled_tokens(raw_text)
    if labeled is not None:
        return build(*labeled)

    known = _split_known_prefix(raw_text.strip(), artists, chars)
    if known is not None:
        return build(*known)

    if len(tokens) >= 3:
        first, second, third = tokens[0], tokens[1], " ".join(tokens[2:])
        # 颠倒容错：先角色后画师
        if looks_char(first) and looks_artist(second):
            return build(second, first, third)
        return build(first, second, third)

    if len(tokens) == 2:
        first, second = tokens[0], tokens[1]
        if looks_char(first) and not looks_artist(second):
            return build("", first, second)
        if looks_artist(first) and not looks_char(second):
            return build(first, "", second)
        if looks_artist(first) and looks_char(second):
            return build(first, second, "")
        if not looks_artist(first) and looks_char(second):
            return build("", second, first)
        return build("", first, second)

    if len(tokens) == 1:
        token = tokens[0]
        if looks_artist(token):
            return build(token, "", "")
        if looks_char(token):
            return build("", token, "")
        return build("", "", token)

    return build("", "", "")


async def _confirm_local_name(bot: Bot, kind: str, raw: str, choices: list[str]) -> str | None:
    """模糊匹配到多个本地名字时列出来让用户选；回别的名字就按新名字创建。"""
    shown = choices[:10]
    listing = "\n".join(f"{index}. {name}" for index, name in enumerate(shown, 1))
    more = f"\n（另有 {len(choices) - len(shown)} 个同名项未列出）" if len(choices) > len(shown) else ""
    resp = await bot.receive_resp(
        f"「{raw}」在本地匹配到多个{kind}：\n{listing}{more}\n回复序号选一个，或回复完整名称按新{kind}创建。",
        timeout=30,
    )
    if resp is None:
        return None
    answer = resp.text.strip()
    if not answer:
        return None
    if answer.isdigit():
        picked = int(answer)
        return shown[picked - 1] if 1 <= picked <= len(shown) else None
    # 回别的名字就按原文返回，由命令层拿完整本地名单再匹配一次
    return answer


@mcbq_admin_sv.on_command(
    (
        "添加表情",
        "导入表情",
        "上传表情",
        "bq添加表情",
        "bq导入表情",
        "bq上传表情",
        "鸣潮添加表情",
        "添加鸣潮表情",
        "上传鸣潮表情",
    ),
    to_ai="添加表情包到本地表情库（需管理权限）",
)
async def cmd_add_pic(bot: Bot, ev: Event) -> None:
    required_pm = get_int("mcbq_upload_pm", 0)
    if ev.user_pm > required_pm:
        logger.debug(f"[MingChaoBQ·导入] 权限不足: user_pm={ev.user_pm} > required_pm={required_pm}")
        return

    index = await load_index()
    plan = _plan_add_pic(ev.text, index)
    artists, chars = _local_names(index)

    if plan["artist_choices"]:
        picked = await _confirm_local_name(bot, "画师", plan["artist"], plan["artist_choices"])
        if picked is None:
            await bot.send("已取消：没有选定画师。")
            return
        # 用户可能回的是本地另一个已有名字，按完整名单重新判定，别误报"新建/命中"
        hit, _ = _lookup_local(picked, artists)
        plan["artist"] = hit or picked
        plan["artist_local"] = bool(hit)
    if plan["role_choices"]:
        picked = await _confirm_local_name(bot, "角色", plan["role"], plan["role_choices"])
        if picked is None:
            await bot.send("已取消：没有选定角色。")
            return
        hit, _ = _lookup_local(picked, chars)
        plan["role"] = hit or picked
        plan["role_local"] = bool(hit)

    artist_clean = safe_name(plan["artist"]) if plan["artist"] else ""
    role_clean = safe_name(plan["role"]) if plan["role"] else ""
    emotion_clean = safe_name(plan["emotion"]) if plan["emotion"] else ""
    for label, raw, cleaned in (("画师", plan["artist"], artist_clean), ("角色", plan["role"], role_clean)):
        if raw and not cleaned:
            await bot.send(f"{label}名包含非法字符，请重新输入。")
            return
    if plan["emotion"] and not emotion_clean:
        await bot.send("表情名包含非法字符，请重新输入。")
        return

    img_bytes = await _extract_image_bytes(bot, ev)
    if not img_bytes:
        await bot.send("未接收到有效的图片文件，添加取消。")
        return

    # 给到哪层就存哪层：只给画师就放画师目录，只给角色时挂到「自定义」下
    if artist_clean and role_clean:
        save_dir = BQ_ROOT / artist_clean / role_clean
    elif artist_clean:
        save_dir = BQ_ROOT / artist_clean
    elif role_clean:
        save_dir = BQ_ROOT / _DEFAULT_ARTIST / role_clean
    else:
        save_dir = BQ_ROOT / _DEFAULT_ARTIST / _DEFAULT_ROLE

    created_dir = not save_dir.exists()
    save_dir.mkdir(parents=True, exist_ok=True)

    ext = _detect_image_suffix(img_bytes)
    if not emotion_clean:
        emotion_clean = _unique_stem(save_dir, f"表情_{int(time.time()) % 10000}", ext)
    target_file = save_dir / f"{emotion_clean}{ext}"
    overwrote = target_file.exists()

    async with aiofiles.open(target_file, "wb") as f:
        await f.write(img_bytes)

    try:
        await rebuild_index()
    except OSError as e:
        logger.warning(f"[MingChaoBQ·导入] 重建索引异常: {e}")

    artist_show = plan["artist"] or _DEFAULT_ARTIST
    role_show = plan["role"] or _DEFAULT_ROLE
    matched = [
        f"{kind}「{name}」用了本地已有目录"
        for kind, name, local in (
            ("画师", plan["artist"], plan["artist_local"]),
            ("角色", plan["role"], plan["role_local"]),
        )
        if name and local
    ]
    created = []
    if created_dir and artist_clean and not role_clean:
        created.append(f"新建画师目录「{artist_show}」")
    elif created_dir and not artist_clean and role_clean:
        created.append(f"在「{_DEFAULT_ARTIST}」下新建角色目录「{role_show}」")
    elif created_dir and artist_clean and role_clean:
        created.append(f"新建目录「{artist_show}/{role_show}」")
    tips = "；".join(matched + created)
    if overwrote:
        tips = f"{tips}；覆盖了同名文件" if tips else "覆盖了同名文件"
    await bot.send(
        f"✅ 已添加：【{artist_show}】{role_show} · {target_file.stem}\n"
        f"位置：{target_file.relative_to(BQ_ROOT).as_posix()}" + (f"\n{tips}" if tips else "")
    )


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
