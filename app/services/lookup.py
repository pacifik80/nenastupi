import asyncio
import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.cache import get_cached, set_cached
from app.services.logging import log_api_error
from app.services.session_log import log_session_event
from app.services.sources.efrsb import EfrsbClient
from app.services.sources.fns import FnsClient
from app.services.sources.hh import HhClient
from app.services.sources.kad import KadClient
from app.services.sources.kontur import KonturClient
from app.services.sources.rusprofile import RusprofileClient
from app.services.sources.zakupki import ZakupkiClient

SOURCE_WEIGHTS = {
    "fns": 1.0,
    "kontur": 0.9,
    "zakupki": 0.8,
    "hh": 0.7,
    "rusprofile": 0.6,
    "kad": 0.7,
    "efrsb": 0.6,
}

SOURCE_URL_TEMPLATES = {
    "fns": "https://egrul.nalog.ru/search?query={query}",
    "kontur": "https://focus-api.kontur.ru/api3/search?query={query}",
    "hh": "https://api.hh.ru/employers?text={query}",
    "rusprofile": "https://www.rusprofile.ru/search?query={query}",
    "zakupki": "https://zakupki.gov.ru/epz/contract/search/results.html?searchString={query}",
    "kad": "https://kad.arbitr.ru/CardService.asmx",
    "efrsb": "https://bankrot.fedresurs.ru/search?text={query}",
}


@dataclass
class Candidate:
    ogrn: Optional[str]
    inn: Optional[str]
    name_full: Optional[str]
    name_short: Optional[str]
    status: Optional[str]
    source: str
    confidence: float


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"\b(\u043e\u043e\u043e|\u043e\u0430\u043e|\u0437\u0430\u043e|\u043f\u0430\u043e|\u0430\u043e|\u0438\u043f|\u043d\u043f|\u0444\u0433\u0443\u043f|\u043c\u0443\u043f)\b", "", name)
    name = re.sub(r"[^a-z\u0430-\u044f0-9 ]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _dice(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    def bigrams(s: str):
        return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}

    ba = bigrams(a)
    bb = bigrams(b)
    overlap = len(ba & bb)
    return (2 * overlap) / (len(ba) + len(bb)) if (ba and bb) else 0.0


def _canonical_key(c: Candidate) -> str:
    if c.ogrn:
        return f"ru:ogrn:{c.ogrn}"
    if c.inn:
        return f"ru:inn:{c.inn}"
    norm = _normalize_name(c.name_full or c.name_short or "")
    return f"name:{hashlib.sha256(norm.encode('utf-8')).hexdigest()[:16]}"


def _calc_confidence(base: float, weight: float, name_match: float, has_ogrn: bool, has_inn: bool) -> float:
    match_coef = 1.0 if has_ogrn else (0.9 if has_inn else max(0.5, name_match))
    return base * weight * match_coef


def _build_candidate(row: dict, source: str, base_conf: float) -> Candidate:
    name_full = row.get("name_full") or row.get("name")
    name_short = row.get("name_short")
    ogrn = row.get("ogrn")
    inn = row.get("inn")
    status = row.get("status")
    weight = SOURCE_WEIGHTS.get(source, 0.5)
    name_match = _dice(_normalize_name(name_full or ""), _normalize_name(name_short or ""))
    conf = _calc_confidence(base_conf, weight, name_match, bool(ogrn), bool(inn))
    return Candidate(ogrn, inn, name_full, name_short, status, source, conf)


def _aggregate(candidates: List[Candidate]) -> List[dict]:
    groups: Dict[str, List[Candidate]] = {}
    for c in candidates:
        groups.setdefault(_canonical_key(c), []).append(c)

    results = []
    for group in groups.values():
        score = sum(c.confidence for c in group)
        top = max(group, key=lambda x: x.confidence)
        results.append({
            "ogrn": top.ogrn,
            "inn": top.inn,
            "name_full": top.name_full,
            "name_short": top.name_short,
            "status": top.status,
            "confidence": min(score / max(1, len(group)), 1.0),
            "sources": sorted({c.source for c in group}),
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results


def _cache_key(query: str) -> str:
    norm = _normalize_name(query)
    h = hashlib.sha256(norm.encode('utf-8')).hexdigest()
    return f"entity:{h}"


def get_cached_lookup(query: str):
    return get_cached(_cache_key(query))


def set_cached_lookup(query: str, payload: dict, ttl: int = 86400):
    set_cached(_cache_key(query), payload, ttl=ttl)


async def _fns_with_retry(client: FnsClient, query: str) -> Tuple[list, Optional[dict]]:
    retries = 3
    for attempt in range(retries):
        rows, err = await client.search_with_status(query)
        if err is None:
            return rows, None
        if err.get("code") in ("timeout", "network", "bad_response", "http_error") and attempt < retries - 1:
            await asyncio.sleep(2 ** attempt)
            continue
        return [], err
    return [], {"code": "timeout", "detail": "max_retries_exceeded"}


async def lookup_company(
    query: str,
    session_id: int | None = None,
    telegram_chat_id: str | None = None,
    telegram_tag: str | None = None,
) -> dict:
    cached = get_cached_lookup(query)
    if cached:
        log_session_event(session_id, telegram_chat_id, telegram_tag, "lookup_cache", "Cache hit for lookup", {"query": query})
        return cached

    fns = FnsClient(settings.fns_base_url, settings.request_timeout)
    kontur = KonturClient(settings.kontur_api_key, settings.request_timeout)
    hh = HhClient(settings.hh_user_agent, settings.request_timeout)
    rusprofile = RusprofileClient(settings.request_timeout)
    zakupki = ZakupkiClient(settings.request_timeout)
    kad = KadClient(settings.request_timeout)
    efrsb = EfrsbClient(settings.efrsb_base_url, settings.request_timeout)

    tasks = [
        _fns_with_retry(fns, query),
        kontur.search(query),
        hh.search(query),
        rusprofile.search(query),
        zakupki.search(query),
        kad.search(query),
        efrsb.search(query),
    ]

    raw = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: List[Candidate] = []
    fns_rows, fns_err = raw[0] if isinstance(raw[0], tuple) else ([], None)
    if fns_err:
        url = SOURCE_URL_TEMPLATES["fns"].format(query=query)
        log_api_error("fns", f"lookup error: {fns_err.get('code')} {fns_err.get('detail','')} url={url} query={query}")
        log_session_event(session_id, telegram_chat_id, telegram_tag, "lookup_fns_error", str(fns_err), {"url": url, "query": query})
    for row in fns_rows:
        candidates.append(_build_candidate(row, "fns", 1.0))
    log_session_event(session_id, telegram_chat_id, telegram_tag, "lookup_fns", f"FNS results: {len(fns_rows)}", {"count": len(fns_rows)})

    sources = ["kontur", "hh", "rusprofile", "zakupki", "kad", "efrsb"]
    for idx, source in enumerate(sources, 1):
        rows = raw[idx]
        if isinstance(rows, Exception):
            url = SOURCE_URL_TEMPLATES.get(source, "")
            url = url.format(query=query) if "{query}" in url else url
            log_api_error(source, f"lookup exception: {type(rows).__name__}: {rows} url={url} query={query}")
            log_session_event(
                session_id,
                telegram_chat_id,
                telegram_tag,
                f"lookup_{source}_error",
                f"{type(rows).__name__}: {rows}",
                {"url": url, "query": query},
            )
            continue
        for row in rows:
            candidates.append(_build_candidate(row, source, 0.7))
        sample = rows[:2] if isinstance(rows, list) else []
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            f"lookup_{source}",
            f"{source} results: {len(rows)}",
            {"count": len(rows), "sample": sample},
        )

    results = _aggregate(candidates)
    log_session_event(session_id, telegram_chat_id, telegram_tag, "lookup_aggregate", f"Aggregated candidates: {len(results)}", {"count": len(results)})

    payload = {
        "query": query,
        "candidates": results,
        "fns_error": fns_err,
    }
    set_cached_lookup(query, payload)
    return payload
