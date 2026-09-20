import asyncio
import shutil

from urllib.parse import urljoin

import aiohttp


class BqApiClient:
    def __init__(
        self,
        base_url="https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games",
        token="",
        random_path="/v1alpha1/random",
        character_param="character",
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        if not random_path.startswith("/"):
            random_path = "/" + random_path
        self.random_path = random_path
        self.character_param = character_param

    def _headers(self):
        """用于 random 端点（emoji.wuwa.games）的请求头。"""
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://emoji.wuwa.games/",
        }
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    async def fetch_random_json(self, role="", max_retry=3):
        """
        从 random 端点获取一条 JSON。
        加入 DNS 抖动重试：偶发 getaddrinfo failed 时自动重试。
        """
        url = self.base_url + self.random_path
        params = {}
        if role:
            params[self.character_param] = role

        data = None
        last_err = None

        for attempt in range(max_retry):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, params=params, headers=self._headers(), timeout=20
                    ) as r:
                        if r.status != 200:
                            print(f"[MingChaoBQ fetch] status={r.status} url={url}")
                            try:
                                err = await r.text()
                                print(f"[MingChaoBQ fetch] error body: {err[:200]}")
                            except Exception:
                                pass
                            return None
                        try:
                            data = await r.json(content_type=None)
                        except Exception:
                            return None
                break  # 成功拿到 data，跳出重试循环

            except aiohttp.ClientConnectorDNSError as e:
                last_err = e
                print(
                    f"[MingChaoBQ fetch] DNS 解析失败，重试 "
                    f"{attempt + 1}/{max_retry}"
                )
                await asyncio.sleep(0.8)

            except Exception as e:
                print(f"[MingChaoBQ fetch error] {repr(e)}")
                return None

        if data is None:
            print(f"[MingChaoBQ fetch] 重试耗尽，最后错误: {repr(last_err)}")
            return None

        # ===== 解析 JSON =====
        if not isinstance(data, dict):
            return None

        img_url = data.get("url") or ""
        if not img_url:
            return None

        char_raw = data.get("character") or data.get("role") or ""
        if isinstance(char_raw, dict):
            role_name = char_raw.get("name") or char_raw.get("slug") or role or "未知角色"
        elif isinstance(char_raw, str):
            role_name = char_raw or role or "未知角色"
        else:
            role_name = role or "未知角色"

        fmt = (data.get("format") or "").lower()
        if fmt in ("gif", "png", "jpg", "jpeg", "webp"):
            suffix = "." + fmt
        else:
            suffix = ".gif"

        return {
            "url": str(img_url),
            "name": str(data.get("id") or "未命名"),
            "role": str(role_name),
            "suffix": suffix,
        }

    async def download(self, url, save_path):
        """
        用系统 curl 下载图片。
        media.wuwa.games 有 Cloudflare 保护，aiohttp 的 TLS 指纹会被识别拦截（返回 567 + HTML）。
        curl 的 TLS 指纹接近浏览器，能稳定通过。
        注意：不传 --compressed，让服务端返回未压缩的原始字节流。
        """
        if url.startswith("//"):
            url = "https:" + url

        curl_bin = shutil.which("curl")
        if not curl_bin:
            print("[MingChaoBQ download] 系统中找不到 curl 命令")
            return False

        save_path.parent.mkdir(parents=True, exist_ok=True)

        headers_args = [
            "-H", "Referer: https://emoji.wuwa.games/",
            "-H", (
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "-H", "Accept: image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "-H", "Accept-Language: zh-CN,zh;q=0.9",
            "-H", "Accept-Encoding: identity",  # 明确要求不压缩
        ]

        for attempt in range(3):
            proc = await asyncio.create_subprocess_exec(
                curl_bin,
                "-sSL",              # 静默 + 跟随重定向
                "--max-time", "30",
                *headers_args,
                "-o", str(save_path),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            ok = (
                proc.returncode == 0
                and save_path.exists()
                and save_path.stat().st_size > 0
            )

            if ok:
                # 校验返回内容不是 Cloudflare 的 HTML 拦截页
                head = save_path.read_bytes()[:32].lstrip().lower()
                if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                    print(
                        f"[MingChaoBQ download] attempt {attempt + 1}: "
                        f"收到 HTML 拦截页，重试"
                    )
                    save_path.unlink(missing_ok=True)
                    continue
                print(
                    f"[MingChaoBQ download] 成功，size={save_path.stat().st_size} bytes"
                )
                return True

            print(
                f"[MingChaoBQ download] attempt {attempt + 1} 失败 "
                f"rc={proc.returncode} "
                f"stderr={stderr.decode(errors='ignore')[:200]}"
            )

        return False