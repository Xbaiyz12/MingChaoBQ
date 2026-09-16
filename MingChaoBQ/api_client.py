import aiohttp
from pathlib import Path


class BqApiClient:
    def __init__(self, config: dict):
        self.base_url = config["base_url"].rstrip("/")
        self.token = config.get("token", "")
        self.list_path = config.get("list_path", "/list")
        self.method = config.get("method", "GET").upper()
        self.headers = config.get("headers", {})
        self.data_path = config.get("data_path", "")
        self.artist_field = config.get("artist_field", "artist")
        self.char_field = config.get("char_field", "character")
        self.name_field = config.get("name_field", "name")
        self.url_field = config.get("url_field", "url")

    def _headers(self):
        h = {"User-Agent": "Mozilla/5.0", **self.headers}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _pick(self, obj, path: str, default=""):
        """从嵌套 dict 里按点分路径取值，例：a.b.c"""
        if not path:
            return default
        cur = obj
        for key in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(key)
            else:
                return default
            if cur is None:
                return default
        return cur

    async def fetch_all(self) -> list:
        """拉取全部条目，返回标准化后的 list[dict]"""
        url = f"{self.base_url}{self.list_path}"
        async with aiohttp.ClientSession() as session:
            if self.method == "POST":
                async with session.post(url, headers=self._headers()) as r:
                    raw = await r.json()
            else:
                async with session.get(url, headers=self._headers()) as r:
                    raw = await r.json()

        data = self._pick(raw, self.data_path, []) if self.data_path else raw
        if not isinstance(data, list):
            return []

        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            result.append({
                "artist": str(self._pick(item, self.artist_field, "未分类画师")),
                "character": str(self._pick(item, self.char_field, "未分类角色")),
                "name": str(self._pick(item, self.name_field, "未命名")),
                "url": str(self._pick(item, self.url_field, "")),
            })
        return result

    async def download(self, url: str, save_path: Path) -> bool:
        if url.startswith("//"):
            url = "https:" + url
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers(), timeout=30) as r:
                    if r.status != 200:
                        return False
                    content = await r.read()
                    if not content:
                        return False
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(content)
                    return True
        except Exception:
            return False