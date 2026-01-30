from datetime import datetime
from app.core.config import settings
from app.services.demo_data import find_demo_company
from app.services.sources.fns import FnsClient
from app.services.sources.efrsb import EfrsbClient
from app.services.sources.news import NewsClient
from app.services.risk import calculate_risks
from app.services.report import build_report
from app.services.cache import get_cached, set_cached


async def check_company(query: str):
    cached = get_cached(query)
    if cached:
        return cached

    fns = FnsClient(settings.fns_base_url, settings.request_timeout)
    efrsb = EfrsbClient(settings.efrsb_base_url, settings.request_timeout)
    news = NewsClient(settings.request_timeout)

    companies = await fns.search(query)
    company = companies[0] if companies else None

    if not company and settings.allow_demo_fallback:
        company = find_demo_company(query)

    if not company:
        return {"ok": False, "error": "company_not_found"}

    bankruptcy = await efrsb.check_bankruptcy(company.get("inn") or company.get("ogrn"))
    news_items, _ = await news.search_employer_news(company.get("name_short") or company.get("name_full"))

    risks = calculate_risks(company, bankruptcy, news_items)
    report = build_report(company, risks, news_items, None)

    payload = {
        "ok": True,
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "company": company,
        "bankruptcy": bankruptcy,
        "news": news_items,
        "risks": risks,
        "report": report,
    }
    set_cached(query, payload)
    return payload
