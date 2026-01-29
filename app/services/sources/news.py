import datetime as dt
import feedparser
import httpx

NEGATIVE_KEYWORDS = [
    "???????",
    "????????",
    "????????",
    "???????",
    "????????",
    "?????",
    "????????",
]


class NewsClient:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search_google_rss(self, query: str, days: int = 90, limit: int = 10):
        since = (dt.datetime.utcnow() - dt.timedelta(days=days)).date().isoformat()
        q = f"{query} when:{since}".strip()
        url = "https://news.google.com/rss/search"
        params = {"q": q, "hl": "ru", "gl": "RU", "ceid": "RU:ru"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": "nenastupi/1.0"})
            resp.raise_for_status()
            data = resp.text
        feed = feedparser.parse(data)
        items = []
        for entry in feed.entries[:limit]:
            published = entry.get("published") or entry.get("updated")
            title = entry.get("title")
            link = entry.get("link")
            summary = entry.get("summary", "")
            items.append({
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "negative": self._is_negative(title or "", summary or ""),
            })
        return items

    def _is_negative(self, title: str, summary: str) -> bool:
        text = f"{title} {summary}".lower()
        return any(k in text for k in NEGATIVE_KEYWORDS)
