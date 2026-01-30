import asyncio
import httpx
from bs4 import BeautifulSoup
from app.services.logging import log_api_error


class ZakupkiClient:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search(self, query: str):
        await asyncio.sleep(2)
        url = "https://zakupki.gov.ru/epz/contract/search/results.html"
        params = {"searchString": query}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": "nenastupi/1.0"})
                if resp.status_code != 200:
                    log_api_error("zakupki", f"url={resp.url} status={resp.status_code}")
                    return []
                html = resp.text
        except Exception as e:
            log_api_error("zakupki", f"url={url} error={type(e).__name__}: {e}")
            return []
        soup = BeautifulSoup(html, "lxml")
        results = []
        for row in soup.select(".registry-entry")[:5]:
            name = row.select_one(".registry-entry__body-value")
            if not name:
                continue
            results.append({
                "name_full": name.get_text(strip=True),
                "name_short": name.get_text(strip=True),
                "inn": None,
                "ogrn": None,
                "status": None,
            })
        return results
