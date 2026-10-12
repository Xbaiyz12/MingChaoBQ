"""内置表情包：首次使用时从发布地址下载并解压进图库，让新用户开箱就有图。"""

import json
import shutil
import zipfile
from pathlib import Path

import aiohttp
import aiofiles

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from .utils.cache import CACHE_DIR
from .utils.paths import BQ_ROOT, BUILTIN_MARKER, SUPPORTED_EXTS
from .mingchao_config import get_str, get_bool

# 发布包地址（GitHub Release 附件），控制台可用 mcbq_builtin_pack_url 覆盖
DEFAULT_PACK_URL = "https://github.com/Xbaiyz12/MingChaoBQ/releases/download/bq-builtin-v1/builtin-bq.zip"
PACK_VERSION = "bq-builtin-v1"
# 单张表情包不该超过这个体积，超过说明包被塞了奇怪的东西
_MAX_ENTRY_BYTES = 60 * 1024 * 1024


def installed_version() -> str:
    """已安装的内置包版本，没装过或标记损坏时返回空串。"""
    if not BUILTIN_MARKER.exists():
        return ""
    try:
        raw: object = json.loads(BUILTIN_MARKER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(raw, dict):
        return ""
    version = raw.get("version")
    return version if isinstance(version, str) else ""


def need_install() -> bool:
    """标记版本与当前包版本不一致就要装（用户删过图也仍算已装，避免反复下载）。"""
    return installed_version() != PACK_VERSION


def _write_marker(version: str, added: int) -> None:
    payload = json.dumps({"version": version, "added": added}, ensure_ascii=False, indent=2)
    BUILTIN_MARKER.write_text(payload, encoding="utf-8")


async def _download(url: str, target: Path) -> bool:
    """流式下载到 target；包有上百 MB，所以给足超时并分块写盘。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=3600, sock_read=180)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[MingChaoBQ·内置包] 下载失败 HTTP {resp.status}: {url}")
                    return False
                async with aiofiles.open(target, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1 << 16):
                        await f.write(chunk)
    except (aiohttp.ClientError, OSError, TimeoutError) as e:
        logger.warning(f"[MingChaoBQ·内置包] 下载异常: {e}")
        return False
    return target.stat().st_size > 0


@to_thread
def _extract(archive: Path, target_root: Path) -> int:
    """把包里的图片解压进图库，跳过已存在的文件（不覆盖用户自己的图）。"""
    added = 0
    target_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            # 只接受「画师/角色/文件」这类相对路径，挡住 zip slip 与绝对路径
            if not parts or ".." in parts or name.startswith("/"):
                logger.warning(f"[MingChaoBQ·内置包] 跳过可疑条目: {name}")
                continue
            dest = target_root.joinpath(*parts)
            if dest.suffix.lower() not in SUPPORTED_EXTS:
                continue
            if dest.exists():
                continue
            if info.file_size > _MAX_ENTRY_BYTES:
                logger.warning(f"[MingChaoBQ·内置包] 跳过超大条目: {name} ({info.file_size} B)")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            added += 1
    return added


async def ensure_pack(force: bool = False) -> tuple[bool, str]:
    """确保内置包就绪，返回 (本次是否新装了内容, 给用户看的说明)。

    force=True 时忽略「已装过」与自动下载开关，用于手动命令重装/补齐。
    """
    if not force:
        if not need_install():
            return False, ""
        if not get_bool("mcbq_builtin_auto_fetch"):
            return False, ""

    url = get_str("mcbq_builtin_pack_url") or DEFAULT_PACK_URL
    archive = CACHE_DIR / "builtin_pack.zip"
    logger.info(f"[MingChaoBQ·内置包] 开始下载: {url}")

    if not await _download(url, archive):
        return False, "⚠️ 内置表情包下载失败，可稍后再发 bq下载表情包 重试。"

    try:
        added = await _extract(archive, BQ_ROOT)
    except (OSError, zipfile.BadZipFile) as e:
        logger.warning(f"[MingChaoBQ·内置包] 解压失败: {e}")
        return False, "⚠️ 内置表情包解压失败，可稍后再发 bq下载表情包 重试。"
    finally:
        archive.unlink(missing_ok=True)

    _write_marker(PACK_VERSION, added)
    logger.info(f"[MingChaoBQ·内置包] 安装完成，新增 {added} 张")
    if added == 0:
        return True, "📦 内置表情包已是最新（没有新增文件）。"
    return True, f"📦 内置表情包安装完成，新增 {added} 张表情。"
