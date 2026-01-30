import httpx
from bs4 import BeautifulSoup


class EfrsbClient:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def check_bankruptcy(self, inn_or_ogrn: str):
        if not inn_or_ogrn:
            return {"found": False, "entries": []}
        url = f"{self.base_url}/search"  # placeholder fallback
        params = {"text": inn_or_ogrn}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": "nenastupi/1.0"})
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            return {"found": False, "entries": [], "note": f"fetch_failed: {type(e).__name__}"}

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True).lower()
        found = "банкрот" in text or "несостоятель" in text
        entries = []
        if found:
            entries.append({"source": url, "note": "keyword_match"})
        return {"found": found, "entries": entries}

    async def search(self, query: str):
        # EFRSB is not a primary registry for entity lookup; return empty results for now.
        return []
