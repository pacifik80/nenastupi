import datetime as dt
from email.utils import parsedate_to_datetime
from typing import Iterable

import feedparser
import httpx

from app.services.sources.deepseek import DeepSeekClient

HR_KEYWORDS = [
    "кадров",
    "назначен",
    "назначение",
    "генеральный директор",
    "CEO",
    "СЕО",
    "руководител",
    "топ-менедж",
    "директор",
    "совет директоров",
    "увольнен",
    "сокращен",
    "оптимизац",
    "массовые сокращения",
    "наем",
    "найм",
    "набор персонала",
    "вакансии",
    "открытие направления",
    "новое направление",
    "реорганизац",
]

RISK_KEYWORDS = [
    "суд",
    "иск",
    "арбитраж",
    "банкрот",
    "ликвидац",
    "штраф",
    "мошеннич",
    "обман",
    "уголовное дело",
    "прокуратур",
    "ФАС",
    "ФНС",
    "проверка",
    "санкц",
]


class NewsClient:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search_google_rss(self, query: str, days: int = 90, limit: int = 10):
        return await self._fetch_google_rss(query, days=days, limit=limit)

    async def search_employer_news(
        self,
        company: str,
        days: int = 90,
        limit_per_query: int = 10,
        max_items: int = 20,
        use_deepseek: bool = True,
    ) -> tuple[list[dict], dict]:
        queries = []
        used_deepseek = False
        if use_deepseek:
            ds = DeepSeekClient()
            ds_queries = await ds.generate_news_queries(company)
            if ds_queries:
                queries = ds_queries
                used_deepseek = True
        if not queries:
            queries = self._default_queries(company)

        queries = self._sanitize_queries(queries, company)

        items: list[dict] = []
        per_query: dict = {}
        for q in queries:
            fetched = await self._fetch_google_rss(q, days=days, limit=limit_per_query)
            per_query[q] = len(fetched)
            for item in fetched:
                item["query"] = q
                items.append(item)

        fetched_total = len(items)
        items = self._dedupe(items)
        items = [i for i in items if self._is_relevant(i.get("title", ""), i.get("summary", ""))]
        filtered_total = len(items)
        for item in items:
            item["category"] = self._categorize(item.get("title", ""), item.get("summary", ""))
            item["reason"] = self._build_reason(item)

        selected_by_llm = False
        if use_deepseek and items:
            ds = DeepSeekClient()
            ranked = await ds.rank_employer_news(company, items, max_items=max_items)
            if ranked is not None:
                items = ranked
                selected_by_llm = True

        meta = {
            "queries": queries,
            "used_deepseek": used_deepseek,
            "fetched_total": fetched_total,
            "filtered_total": filtered_total,
            "per_query": per_query,
            "selected_by_llm": selected_by_llm,
        }
        return items[:max_items], meta

    async def _fetch_google_rss(self, query: str, days: int = 90, limit: int = 10):
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
            source_name = ""
            try:
                source_name = (entry.get("source") or {}).get("title") or ""
            except Exception:
                source_name = ""
            if not source_name and isinstance(title, str) and " - " in title:
                source_name = title.rsplit(" - ", 1)[-1].strip()
            items.append({
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "negative": self._is_risk(title or "", summary or ""),
                "source": source_name,
            })
        return items

    def _default_queries(self, company: str) -> list[str]:
        base = f"\"{company}\""
        return [
            base + " (назначен OR назначение OR \"генеральный директор\" OR руководител* OR \"совет директоров\" OR \"кадровые изменения\")",
            base + " (сокращение OR увольнение OR \"оптимизация штата\" OR найм OR \"набор персонала\" OR вакансии OR \"открытие направления\" OR \"новое направление\")",
            base + " (суд OR иск OR арбитраж OR банкротство OR штраф OR мошенничество OR проверка OR ФАС OR ФНС OR прокуратура)",
        ]

    def _sanitize_queries(self, queries: list[str], company: str) -> list[str]:
        cleaned = []
        for q in queries:
            if "?" in q:
                continue
            cleaned.append(q)
        if cleaned:
            return cleaned
        return self._default_queries(company)

    def _is_relevant(self, title: str, summary: str) -> bool:
        text = f"{title} {summary}".lower()
        return any(k in text for k in HR_KEYWORDS) or any(k in text for k in RISK_KEYWORDS)

    def _is_risk(self, title: str, summary: str) -> bool:
        text = f"{title} {summary}".lower()
        return any(k in text for k in RISK_KEYWORDS)

    def _categorize(self, title: str, summary: str) -> str:
        text = f"{title} {summary}".lower()
        if any(k in text for k in RISK_KEYWORDS):
            return "risk"
        if any(k in text for k in HR_KEYWORDS):
            return "hr"
        return "other"

    def _build_reason(self, item: dict) -> str:
        text = f"{item.get('title','')} {item.get('summary','')}".lower()
        if any(k in text for k in ["банкрот", "ликвидац"]):
            return "Новость о признаках банкротства/ликвидации."
        if any(k in text for k in ["суд", "иск", "арбитраж", "прокуратур"]):
            return "Новость о судебных разбирательствах или проверках."
        if any(k in text for k in ["штраф", "фас", "фнс", "санкц"]):
            return "Новость о штрафах, санкциях или претензиях регуляторов."
        if any(k in text for k in ["мошеннич", "обман", "уголовное дело"]):
            return "Новость о возможных нарушениях или мошенничестве."
        if any(k in text for k in ["назначен", "назначение", "генеральный директор", "совет директоров", "руководител"]):
            return "Новость о кадровых изменениях в руководстве."
        if any(k in text for k in ["сокращен", "увольнен", "оптимизац", "массовые сокращения"]):
            return "Новость о сокращениях или изменениях численности персонала."
        if any(k in text for k in ["найм", "набор персонала", "вакансии"]):
            return "Новость о найме или расширении штата."
        if any(k in text for k in ["открытие направления", "новое направление", "реорганизац"]):
            return "Новость о запуске/реорганизации направлений бизнеса."
        return "Новость потенциально важна для оценки работодателя."

    @staticmethod
    def format_date(value: str | None) -> str:
        if not value:
            return "дата неизвестна"
        try:
            return parsedate_to_datetime(value).date().isoformat()
        except Exception:
            return "дата неизвестна"

    def _dedupe(self, items: Iterable[dict]) -> list[dict]:
        seen = set()
        out = []
        for item in items:
            key = (item.get("link") or "", item.get("title") or "")
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out
