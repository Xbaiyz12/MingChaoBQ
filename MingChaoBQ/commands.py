"""鸣潮表情包主命令：随机 / 本地随机 / 检索 / 列表 / 帮助 / 戳一戳 / 索引更新。"""

import json
import random
from pathlib import Path

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.data_store import get_res_path

from .api_sync import fetch_and_save, download_to_url
from .whitelist import get_group_role, set_group_role, is_group_allowed
from .api_client import ApiPic
from .utils.cache import new_cache_path
from .utils.paths import BQ_ROOT
from .index_generator import load_index, rebuild_index
from .mingchao_config import get_int, get_bool, set_config, get_str_list
from .utils.image_utils import render_text_to_image
from .utils.index_types import Index, PicEntry
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
    """发送本地图片，根据 source 决定标注格式"""
    full_path = BQ_ROOT / pic["file"]
    if not full_path.exists():
        await bot.send(f"图片文件不存在：{pic['file']}")
        return

    artist = pic.get("_artist", "")
    char = pic.get("_char", "未知角色")
    emotion = pic.get("emotion", "")

    if pic.get("source") == "api" or artist == "API":
        label = f"【API】{char}"
    else:
        label = f"【{artist}】{char} · {emotion}"

    await bot.send([MessageSegment.text(label), MessageSegment.image(full_path)])


async def _try_api(role: str = "") -> ApiPic | None:
    """从 API 获取一张，返回 {"url", "name", "role", ...} 或 None"""
    if not get_bool("mcbq_api_enable"):
        return None
    return await fetch_and_save(role=role)


async def _send_from_api(bot: Bot, data: ApiPic) -> None:
    """发送一张 API 来源的图。优先用落盘缓存；没存下来就现下载到 cache 再发"""
    label = f"【API】{data['role']}"

    saved_path = data.get("saved_path", "")
    if saved_path and Path(saved_path).exists():
        await bot.send([MessageSegment.text(label), MessageSegment.image(Path(saved_path))])
        return

    temp_path = new_cache_path("api", data["suffix"])
    if await download_to_url(data["url"], temp_path):
        await bot.send([MessageSegment.text(label), MessageSegment.image(temp_path)])
        return

    await bot.send(label + "\n（图片下载失败）")


def _load_ww_alias() -> dict[str, str]:
    """读上游鸣潮插件的角色别名表；文件缺失或损坏时当作没有别名。"""
    if not _WW_ALIAS_FILE.exists():
        return {}

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
    return result


def _get_alias_map() -> dict[str, str]:
    result = _load_ww_alias()
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
    return _get_alias_map().get(keyword, keyword)


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

    matched = _match_emotions(index, keyword, fuzzy=False)
    fuzzy = False
    if not matched:
        matched = _match_emotions(index, keyword, fuzzy=True)
        fuzzy = True
    if not matched:
        await bot.send(f"没有找到表情「{keyword}」。换一个词试试吧。")
        return

    lines: list[str] = []
    for pic in matched:
        artist = pic.get("_artist", "")
        char = pic.get("_char", "")
        emotion = pic["emotion"]
        if pic.get("source") == "api" or artist == "API":
            lines.append(f"【API】{char} · {emotion}")
        else:
            lines.append(f"【{artist}】{char} · {emotion}")

    title = f"搜索「{keyword}」共 {len(matched)} 个{'（模糊）' if fuzzy else ''}"
    img_path = await render_text_to_image("\n".join(lines), title=title)
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
