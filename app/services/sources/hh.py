import httpx
from app.services.logging import log_api_error


class HhClient:
    def __init__(self, user_agent: str, timeout: int = 10):
        self.user_agent = user_agent
        self.timeout = timeout

    async def search(self, query: str):
        url = "https://api.hh.ru/employers"
        params = {"text": query, "per_page": 5}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": self.user_agent})
                if resp.status_code != 200:
                    log_api_error("hh", f"url={resp.url} status={resp.status_code}")
                    return []
                data = resp.json()
        except Exception as e:
            log_api_error("hh", f"url={url} error={type(e).__name__}: {e}")
            return []
        results = []
        for item in data.get("items", []):
            results.append({
                "name_full": item.get("name"),
                "name_short": item.get("name"),
                "inn": None,
                "ogrn": None,
                "status": None,
            })
        return results
