"""鸣潮表情包远端 API：取一张随机图的 JSON + 把图下载到本地。"""

import shutil
import asyncio
from typing import TypedDict
from pathlib import Path

import aiohttp
import aiofiles

from gsuid_core.logger import logger
from gsuid_core.server import on_core_shutdown

DEFAULT_BASE = "https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games"
DEFAULT_RANDOM_PATH = "/v1alpha1/random"
DEFAULT_CHARACTER_PARAM = "character"
REFERER = "https://emoji.wuwa.games/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

_ALLOWED_SUFFIX = (".gif", ".png", ".jpg", ".jpeg", ".webp")
_MAX_BYTES = 20 * 1024 * 1024

_session: aiohttp.ClientSession | None = None


def _session_instance() -> aiohttp.ClientSession:
    """复用连接池，避免每次请求都新建 session。只在事件循环内被调用。"""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


@on_core_shutdown
async def close_api_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


class ApiPicInfo(TypedDict):
    url: str
    name: str
    role: str
    suffix: str


class ApiPic(ApiPicInfo, total=False):
    """落盘成功后会补上 saved_path。"""

    saved_path: str


def _looks_like_html(head: bytes) -> bool:
    """Cloudflare 拦截时返回的是 HTML 页而不是图片字节。"""
    head = head.lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


class BqApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE,
        token: str = "",
        random_path: str = DEFAULT_RANDOM_PATH,
        character_param: str = DEFAULT_CHARACTER_PARAM,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.random_path = random_path if random_path.startswith("/") else "/" + random_path
        self.character_param = character_param

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": UA, "Referer": REFERER}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        return headers

    async def fetch_random_json(self, role: str = "", max_retry: int = 3) -> ApiPicInfo | None:
        """取一条随机图 JSON。DNS 偶发解析失败时自动重试。"""
        url = self.base_url + self.random_path
        params: dict[str, str] = {}
        if role:
            params[self.character_param] = role

        data: object = None
        for attempt in range(max_retry):
            try:
                session = _session_instance()
                timeout = aiohttp.ClientTimeout(total=20)
                async with session.get(url, params=params, headers=self._headers(), timeout=timeout) as r:
                    if r.status != 200:
                        body = await r.text()
                        logger.warning(f"[MingChaoBQ·API] status={r.status} url={url} body={body[:200]}")
                        return None
                    data = await r.json(content_type=None)
                break
            except aiohttp.ClientConnectorDNSError as e:
                logger.warning(f"[MingChaoBQ·API] DNS 解析失败，重试 {attempt + 1}/{max_retry}: {e!r}")
                await asyncio.sleep(0.8)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"[MingChaoBQ·API] 请求失败: {e!r}")
                return None
        else:
            logger.warning("[MingChaoBQ·API] 重试耗尽")
            return None

        if not isinstance(data, dict):
            return None

        img_url = data.get("url")
        if not isinstance(img_url, str) or not img_url:
            return None

        char_raw: object = data.get("character") or data.get("role")
        role_name = role or "未知角色"
        if isinstance(char_raw, str) and char_raw:
            role_name = char_raw
        elif isinstance(char_raw, dict):
            name_raw: object = char_raw.get("name") or char_raw.get("slug")
            if isinstance(name_raw, str) and name_raw:
                role_name = name_raw

        fmt_raw: object = data.get("format")
        fmt = fmt_raw.lower() if isinstance(fmt_raw, str) else ""
        suffix = "." + fmt if "." + fmt in _ALLOWED_SUFFIX else ".gif"

        id_raw: object = data.get("id")
        name = str(id_raw) if isinstance(id_raw, (str, int)) else "未命名"

        return ApiPicInfo(url=img_url, name=name, role=role_name, suffix=suffix)

    async def _download_by_curl(self, curl_bin: str, url: str, save_path: Path) -> bool:
        """
        用系统 curl 下载：media.wuwa.games 有 Cloudflare 保护，aiohttp 的 TLS 指纹会被拦（567 + HTML），
        curl 的指纹接近浏览器。不传 --compressed，让服务端返回未压缩的原始字节流。
        """
        proc = await asyncio.create_subprocess_exec(
            curl_bin,
            "-sSL",
            "--max-time",
            "30",
            "-H",
            f"Referer: {REFERER}",
            "-H",
            f"User-Agent: {UA}",
            "-H",
            "Accept: image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "-H",
            "Accept-Language: zh-CN,zh;q=0.9",
            "-H",
            "Accept-Encoding: identity",
            "-o",
            str(save_path),
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not save_path.exists() or save_path.stat().st_size == 0:
            logger.warning(f"[MingChaoBQ·下载] curl 失败 rc={proc.returncode} {stderr.decode(errors='ignore')[:200]}")
            return False

        with open(save_path, "rb") as f:
            head = f.read(32)
        if _looks_like_html(head):
            logger.warning("[MingChaoBQ·下载] curl 拿到 HTML 拦截页")
            save_path.unlink(missing_ok=True)
            return False
        return True

    async def _download_by_aiohttp(self, url: str, save_path: Path) -> bool:
        """curl 不存在（精简镜像）或被拦时的回退路径。"""
        headers = {"User-Agent": UA, "Referer": REFERER, "Accept-Encoding": "identity"}
        timeout = aiohttp.ClientTimeout(total=30)
        try:
            session = _session_instance()
            async with session.get(url, headers=headers, timeout=timeout) as r:
                if r.status != 200:
                    logger.warning(f"[MingChaoBQ·下载] aiohttp status={r.status} url={url}")
                    return False
                content = await r.content.read(_MAX_BYTES + 1)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"[MingChaoBQ·下载] aiohttp 请求失败: {e!r}")
            return False

        if not content or len(content) > _MAX_BYTES:
            logger.warning(f"[MingChaoBQ·下载] aiohttp 返回内容异常 size={len(content)}")
            return False
        if _looks_like_html(content):
            logger.warning("[MingChaoBQ·下载] aiohttp 拿到 HTML 拦截页")
            return False

        save_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)
        return True

    async def download(self, url: str, save_path: Path) -> bool:
        """把一张图下载到 save_path。优先 curl，系统没有 curl 时回退 aiohttp。"""
        if url.startswith("//"):
            url = "https:" + url

        save_path.parent.mkdir(parents=True, exist_ok=True)
        curl_bin = shutil.which("curl")

        for attempt in range(3):
            ok = (
                await self._download_by_curl(curl_bin, url, save_path)
                if curl_bin is not None
                else await self._download_by_aiohttp(url, save_path)
            )
            if ok:
                logger.debug(f"[MingChaoBQ·下载] 成功 {save_path.name} size={save_path.stat().st_size}")
                return True
            logger.warning(f"[MingChaoBQ·下载] 第 {attempt + 1}/3 次失败: {url}")

        if curl_bin is not None:
            logger.info("[MingChaoBQ·下载] curl 重试耗尽，改用 aiohttp 再试一次")
            return await self._download_by_aiohttp(url, save_path)
        return False
