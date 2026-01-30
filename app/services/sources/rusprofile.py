import asyncio
import httpx
from bs4 import BeautifulSoup
from app.services.logging import log_api_error


class RusprofileClient:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search(self, query: str):
        await asyncio.sleep(2)
        url = "https://www.rusprofile.ru/search"
        params = {"query": query}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": "nenastupi/1.0"})
                if resp.status_code != 200:
                    log_api_error("rusprofile", f"url={resp.url} status={resp.status_code}")
                    return []
                html = resp.text
        except Exception as e:
            log_api_error("rusprofile", f"url={url} error={type(e).__name__}: {e}")
            return []
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select(".company-item")[:5]:
            name = card.select_one(".company-item__title")
            inn = card.select_one(".company-item__inn")
            ogrn = card.select_one(".company-item__ogrn")
            results.append({
                "name_full": name.get_text(strip=True) if name else None,
                "name_short": name.get_text(strip=True) if name else None,
                "inn": inn.get_text(strip=True).replace("ИНН ", "") if inn else None,
                "ogrn": ogrn.get_text(strip=True).replace("ОГРН ", "") if ogrn else None,
                "status": None,
            })
        return results
