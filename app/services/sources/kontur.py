import httpx


class KonturClient:
    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout

    async def search(self, query: str):
        if not self.api_key:
            return []
        url = "https://focus-api.kontur.ru/api3/search"
        params = {"query": query, "key": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
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
        return results
