import httpx
from app.services.logging import log_api_error


class KonturClient:
    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout

    async def search(self, query: str):
        results, _ = await self.search_with_status(query)
        return results

    async def search_with_status(self, query: str):
        if not self.api_key:
            return [], {"status": "missing_key"}
        url = "https://focus-api.kontur.ru/api3/search"
        params = {"query": query, "key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    log_api_error("kontur", f"url={resp.url} status={resp.status_code}")
                    return [], {"url": url, "query": query, "status": resp.status_code, "body": resp.text[:2000]}
                data = resp.json()
        except Exception as e:
            log_api_error("kontur", f"url={url} error={type(e).__name__}: {e}")
            return [], {"url": url, "query": query, "status": "error", "error": type(e).__name__}
        results = []
        for item in data.get("items", []):
            req = item.get("req") or {}
            results.append({
                "ogrn": req.get("ogrn"),
                "inn": req.get("inn"),
                "name_full": req.get("fullName"),
                "name_short": req.get("shortName"),
                "status": req.get("status"),
            })
        return results, {"url": url, "query": query, "status": resp.status_code, "count": len(results), "body": resp.text[:2000]}
