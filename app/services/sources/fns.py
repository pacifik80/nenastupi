import httpx


class FnsClient:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: str):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = None
            try:
                r = await client.post(
                    f"{self.base_url}/",
                    data={"query": query},
                    headers={"User-Agent": "nenastupi/1.0"},
                )
                r.raise_for_status()
                data = r.json()
                token = data.get("t")
            except Exception:
                token = None

            candidates = []
            urls = []
            if token:
                urls.extend([
                    f"{self.base_url}/search?query={query}&t={token}",
                    f"{self.base_url}/search?req={token}",
                    f"{self.base_url}/search?t={token}",
                ])
            urls.append(f"{self.base_url}/search?query={query}")

            for url in urls:
                try:
                    resp = await client.get(url, headers={"User-Agent": "nenastupi/1.0"})
                    resp.raise_for_status()
                    data = resp.json()
                    rows = data.get("rows") or data.get("items") or []
                    for row in rows:
                        candidates.append(self._normalize(row))
                    if candidates:
                        break
                except Exception:
                    continue

            return candidates

    def _normalize(self, row: dict):
        return {
            "ogrn": row.get("o") or row.get("ogrn") or row.get("ОГРН"),
            "inn": row.get("i") or row.get("inn") or row.get("ИНН"),
            "name_full": row.get("n") or row.get("name") or row.get("НаимПолн"),
            "name_short": row.get("c") or row.get("short") or row.get("НаимСокр"),
            "status": row.get("s") or row.get("status") or row.get("Статус"),
            "reg_date": row.get("r") or row.get("reg_date") or row.get("ДатаРег"),
        }
