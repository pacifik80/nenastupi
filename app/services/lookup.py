import hashlib
import re
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.cache import get_cached, set_cached
from app.services.logging import log_api_error
from app.services.session_log import log_session_event
from app.services.sources.deepseek import DeepSeekClient
from app.services.sources.fns import FnsClient
from app.services.sources.kontur import KonturClient
from app.services.sources.yandex_search import YandexSearchClient


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
    name = re.sub(r"\\b(ооо|оао|зао|пао|ао|ип|нп|фгуп|муп)\\b", "", name)
    name = re.sub(r"[^a-zа-я0-9 ]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


COMMON_TYPOS = {
    "яндкс": "яндекс",
    "сбрбанк": "сбербанк",
    "сбр": "сбер",
    "тинькоф": "тинькофф",
    "мгнит": "магнит",
}


def _apply_typo_map(query: str) -> str:
    q = query.lower().strip()
    return COMMON_TYPOS.get(q, q)


def _cache_get(key: str):
    return get_cached(key)


def _cache_set(key: str, payload: dict | str, ttl: int):
    set_cached(key, payload, ttl=ttl)


def _cache_key(kind: str, value: str) -> str:
    h = hashlib.sha256(value.encode('utf-8')).hexdigest()
    return f"{kind}:{h}"


def _is_url(query: str) -> bool:
    value = query.strip()
    if not value:
        return False
    if re.search(r"^https?://", value, re.IGNORECASE):
        return True
    if value.lower().startswith("www."):
        return True
    if "/" in value:
        return True
    return False


def _extract_domain(query: str) -> str:
    value = query.strip()
    if not value:
        return ""
    if not re.search(r"^https?://", value, re.IGNORECASE):
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc or parsed.path
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    host = host.strip("/")
    return host


def _validate_inn10(inn: str) -> bool:
    if not re.match(r"^\d{10}$", inn):
        return False
    nums = list(map(int, inn))
    checksum = (2*nums[0] + 4*nums[1] + 10*nums[2] + 3*nums[3] + 5*nums[4] + 9*nums[5] + 4*nums[6] + 6*nums[7] + 8*nums[8]) % 11 % 10
    return checksum == nums[9]


def _validate_inn12(inn: str) -> bool:
    if not re.match(r"^\d{12}$", inn):
        return False
    nums = list(map(int, inn))
    checksum1 = (7*nums[0] + 2*nums[1] + 4*nums[2] + 10*nums[3] + 3*nums[4] + 5*nums[5] + 9*nums[6] + 4*nums[7] + 6*nums[8] + 8*nums[9]) % 11 % 10
    checksum2 = (3*nums[0] + 7*nums[1] + 2*nums[2] + 4*nums[3] + 10*nums[4] + 3*nums[5] + 5*nums[6] + 9*nums[7] + 4*nums[8] + 6*nums[9] + 8*nums[10]) % 11 % 10
    return checksum1 == nums[10] and checksum2 == nums[11]


def _validate_ogrn(ogrn: str) -> bool:
    if not re.match(r"^\d{13}$", ogrn):
        return False
    base = int(ogrn[:12])
    return (base % 11) % 10 == int(ogrn[12])


def _validate_ogrnip(ogrn: str) -> bool:
    if not re.match(r"^\d{15}$", ogrn):
        return False
    base = int(ogrn[:14])
    return (base % 13) % 10 == int(ogrn[14])


def _valid_company_number(value: str) -> bool:
    if not value:
        return False
    if re.match(r"^\d{10}$", value):
        return _validate_inn10(value)
    if re.match(r"^\d{12}$", value):
        return _validate_inn12(value)
    if re.match(r"^\d{13}$", value):
        return _validate_ogrn(value)
    if re.match(r"^\d{15}$", value):
        return _validate_ogrnip(value)
    return False


def _classify(query: str) -> str:
    q = query.strip()
    if re.match(r"^\d{10}$", q) and _validate_inn10(q):
        return "inn_legal"
    if re.match(r"^\d{12}$", q) and _validate_inn12(q):
        return "inn_ip"
    if re.match(r"^\d{13}$", q) and _validate_ogrn(q):
        return "ogrn"
    if re.match(r"^\d{15}$", q) and _validate_ogrnip(q):
        return "ogrnip"
    if _is_url(q):
        return "url"
    if re.match(r"^\d+$", q):
        return "invalid_numeric"
    return "name"


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


def _build_candidate(row: dict, source: str, base_conf: float, query_norm: str) -> Candidate:
    name_full = row.get("name_full") or row.get("name")
    name_short = row.get("name_short")
    ogrn = row.get("ogrn")
    inn = row.get("inn")
    status = row.get("status")
    name_match = _dice(query_norm, _normalize_name(name_full or name_short or ""))
    conf = base_conf * name_match if name_match else base_conf
    return Candidate(ogrn, inn, name_full, name_short, status, source, conf)


def _candidate_to_dict(c: Candidate) -> dict:
    return {
        "ogrn": c.ogrn,
        "inn": c.inn,
        "name_full": c.name_full,
        "name_short": c.name_short,
        "status": c.status,
        "source": c.source,
        "confidence": c.confidence,
    }


def _resolve_cache_key(norm: str) -> str:
    return _cache_key("resolve", norm)


def _normalize_cache_key(norm: str) -> str:
    return _cache_key("normalize", norm)


def _llm_cache_key(query: str, candidates: list[dict]) -> str:
    payload = query + ";" + ";".join([c.get("inn") or "" for c in candidates[:3]])
    return _cache_key("llm_resolve", payload)


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"\b\d{10}\b|\b\d{12}\b|\b\d{13}\b|\b\d{15}\b", text)


def _extract_number_counts(snippets: list[str]) -> dict:
    counts: Dict[str, int] = {}
    for s in snippets:
        for num in _extract_numbers(s):
            counts[num] = counts.get(num, 0) + 1
    return counts


def _pick_inn_from_snippets(snippets: list[str]) -> Optional[str]:
    counts = _extract_number_counts(snippets)
    for num, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        if cnt >= 2:
            return num
    return None


def _compact_snippets(snippets: list[str], max_items: int = 8, max_chars: int = 320) -> list[str]:
    compact: list[str] = []
    for raw in snippets:
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        compact.append(text[:max_chars])
        if len(compact) >= max_items:
            break
    return compact


async def _fns_search(query: str) -> tuple[list[dict], Optional[dict]]:
    fns = FnsClient(settings.fns_base_url, settings.request_timeout)
    return await fns.search_with_status(query)


async def _kontur_search(query: str) -> tuple[list[dict], dict]:
    kontur = KonturClient(settings.kontur_api_key, settings.request_timeout)
    return await kontur.search_with_status(query)


async def _resolve_inn_candidate(inn_or_ogrn: str) -> Optional[dict]:
    rows, _, _ = await _fns_search(inn_or_ogrn)
    if not rows:
        return None
    candidate = _build_candidate(rows[0], "fns", 1.0, _normalize_name(rows[0].get("name_full") or ""))
    return _candidate_to_dict(candidate)


def _minimal_candidate_from_inn(query: str, inn_or_ogrn: str, source: str) -> dict:
    return _candidate_to_dict(
        Candidate(
            ogrn=inn_or_ogrn if re.match(r"^\d{13,15}$", inn_or_ogrn) else None,
            inn=inn_or_ogrn if re.match(r"^\d{10,12}$", inn_or_ogrn) else None,
            name_full=query,
            name_short=None,
            status=None,
            source=source,
            confidence=0.45,
        )
    )


async def _agentic_web_lookup(
    query: str,
    search_query: str,
    session_id: int | None,
    telegram_chat_id: str | None,
    telegram_tag: str | None,
    max_steps: int = 2,
) -> Optional[dict]:
    ys = YandexSearchClient()
    ds = DeepSeekClient()
    current_query = search_query
    for step in range(1, max_steps + 1):
        snippets, ymeta = ys.search_web_with_meta(current_query, pages=1, format="xml")
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "yandex_search",
            "Yandex search performed",
            {"query": current_query, "pages": 1, "step": step},
            {"snippets": len(snippets), "meta": ymeta},
        )
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "yandex_search_raw",
            "Yandex raw search payload",
            {"query": current_query, "pages": 1, "step": step},
            {"raw_pages": snippets, "raw_bytes": sum(len(s.encode("utf-8")) for s in snippets)},
        )
        if not snippets:
            return None

        compact = _compact_snippets(snippets)
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "yandex_snippets_compact",
            "Compact snippets prepared",
            {"query": current_query, "step": step, "count": len(compact)},
            {"snippets": compact},
        )
        if ds.is_configured():
            prompt = ds.build_web_prompt(query, current_query, compact, step, max_steps)
            log_session_event(
                session_id,
                telegram_chat_id,
                telegram_tag,
                "deepseek_call",
                "DeepSeek web think",
                {"query": query, "search_query": current_query, "step": step},
                {
                    "snippets": len(compact),
                    "prompt": prompt,
                    "model": ds.model,
                    "api_base": ds.api_base,
                    "temperature": 0.2,
                    "max_steps": max_steps,
                },
            )
            llm_resp = await ds.think_web(query, current_query, compact, step, max_steps)
            log_session_event(
                session_id,
                telegram_chat_id,
                telegram_tag,
                "deepseek_result",
                "DeepSeek web response",
                {"query": query, "search_query": current_query, "step": step},
                llm_resp if llm_resp is not None else {"_error": "no_response"},
            )
            if llm_resp:
                action = (llm_resp.get("action") or "").strip().lower()
                log_session_event(
                    session_id,
                    telegram_chat_id,
                    telegram_tag,
                    "deepseek_action",
                    "DeepSeek action parsed",
                    {"query": query, "search_query": current_query, "step": step},
                    {
                        "action": action,
                        "inn": llm_resp.get("inn"),
                        "clarify": llm_resp.get("clarify"),
                        "search_query": llm_resp.get("search_query"),
                        "ok": llm_resp.get("_ok"),
                        "parse_error": llm_resp.get("_parse_error"),
                    },
                )
                if action == "select":
                    inn = (llm_resp.get("inn") or "").strip()
                    if _valid_company_number(inn):
                        return {
                            "action": "select",
                            "inn": inn,
                            "source": "deepseek_web",
                            "meta": {
                                "deepseek": llm_resp,
                                "yandex": ymeta,
                                "snippets_count": len(snippets),
                            },
                        }
                if action == "clarify":
                    clarify = (llm_resp.get("clarify") or "").strip()
                    if clarify:
                        return {
                            "action": "clarify",
                            "clarify": clarify,
                            "source": "deepseek_web",
                            "meta": {
                                "deepseek": llm_resp,
                                "yandex": ymeta,
                                "snippets_count": len(snippets),
                            },
                        }
                if action == "search":
                    new_query = (llm_resp.get("search_query") or "").strip()
                    if new_query and new_query != current_query:
                        current_query = new_query
                        continue
            else:
                log_session_event(
                    session_id,
                    telegram_chat_id,
                    telegram_tag,
                    "deepseek_action",
                    "DeepSeek action missing",
                    {"query": query, "search_query": current_query, "step": step},
                    {"action": None},
                )
        else:
            log_session_event(
                session_id,
                telegram_chat_id,
                telegram_tag,
                "deepseek_skipped",
                "DeepSeek not configured",
                {"query": query, "search_query": current_query, "step": step},
                {"configured": False},
            )

        counts = _extract_number_counts(snippets)
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "yandex_numbers",
            "Numbers extracted from snippets",
            {"query": current_query, "step": step},
            {"counts": counts},
        )
        inn = _pick_inn_from_snippets(snippets)
        if inn and _valid_company_number(inn):
            log_session_event(
                session_id,
                telegram_chat_id,
                telegram_tag,
                "yandex_snippet_pick",
                "Snippet INN extraction",
                {"query": current_query, "step": step},
                {"inn": inn},
            )
            return {
                "action": "select",
                "inn": inn,
                "source": "yandex_snippets",
                "meta": {"yandex": ymeta},
            }

        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "agentic_no_result",
            "Agentic lookup produced no result for step",
            {"query": query, "search_query": current_query, "step": step},
            None,
        )
        return None

    return None


async def lookup_company(
    query: str,
    session_id: int | None = None,
    telegram_chat_id: str | None = None,
    telegram_tag: str | None = None,
) -> dict:
    log_session_event(
        session_id,
        telegram_chat_id,
        telegram_tag,
        "classify",
        "Classifying query",
        {"query": query},
        None,
    )

    qtype = _classify(query)
    log_session_event(
        session_id,
        telegram_chat_id,
        telegram_tag,
        "classify_result",
        "Query type",
        {"query": query},
        {"type": qtype},
    )
    if qtype == "invalid_numeric":
        return {"status": "clarify", "clarify": "Введите корректный ИНН/ОГРН или название."}

    # Normalize & typo
    typo_key = _cache_key("typo", query.lower().strip())
    typo_cached = _cache_get(typo_key)
    if typo_cached:
        query_norm = typo_cached
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "normalize_typo_cache",
            "Typo cache hit",
            {"query": query},
            {"value": query_norm},
        )
    else:
        query_norm = _apply_typo_map(query)
        _cache_set(typo_key, query_norm, 604800)
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "normalize_typo",
            "Applied typo map",
            {"query": query},
            {"value": query_norm},
        )

    norm_key = _normalize_cache_key(query_norm)
    norm_cached = _cache_get(norm_key)
    if norm_cached:
        query_norm = norm_cached
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "normalize_cache",
            "Normalize cache hit",
            {"query": query},
            {"value": query_norm},
        )
    else:
        query_norm = _normalize_name(query_norm)
        _cache_set(norm_key, query_norm, 604800)
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "normalize",
            "Normalized query",
            {"query": query},
            {"value": query_norm},
        )

    resolve_key = _resolve_cache_key(query_norm)
    resolve_cached = _cache_get(resolve_key)
    if resolve_cached:
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "resolve_cache",
            "Resolve cache hit",
            {"query": query_norm},
            {"key": resolve_key},
        )
        candidate = await _resolve_inn_candidate(resolve_cached)
        if candidate:
            return {"status": "resolved", "candidate": candidate, "source": "cache"}

    # Direct flows
    if qtype in ("inn_legal", "inn_ip", "ogrn", "ogrnip"):
        rows, err, trace = await _fns_search(query)
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "fns_direct",
            "FNS direct results",
            {"query": query},
            {"count": len(rows), "sample": [r.get("name_full") or r.get("name") for r in rows[:3]], "trace": trace},
        )
        if err:
            log_api_error("fns", f"direct error: {err}")
        if rows:
            candidate = _build_candidate(rows[0], "fns", 1.0, _normalize_name(rows[0].get("name_full") or ""))
            _cache_set(resolve_key, candidate.inn or candidate.ogrn or "", 86400)
            return {"status": "resolved", "candidate": _candidate_to_dict(candidate), "source": "fns"}
        kontur_rows, kontur_meta = await _kontur_search(query)
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "kontur_direct",
            "Kontur direct results",
            {"query": query},
            {"count": len(kontur_rows), "sample": [r.get("name_full") or r.get("name") for r in kontur_rows[:3]], "meta": kontur_meta},
        )
        if kontur_rows:
            candidate = _build_candidate(kontur_rows[0], "kontur", 1.0, _normalize_name(kontur_rows[0].get("name_full") or ""))
            _cache_set(resolve_key, candidate.inn or candidate.ogrn or "", 86400)
            return {"status": "resolved", "candidate": _candidate_to_dict(candidate), "source": "kontur"}
        return {"status": "not_found"}

    # URL flow -> agentic web lookup
    if qtype == "url":
        domain = _extract_domain(query)
        search_query = f"{domain or query_norm} официальный сайт ИНН"
        agent_result = await _agentic_web_lookup(
            domain or query_norm,
            search_query,
            session_id,
            telegram_chat_id,
            telegram_tag,
        )
        if agent_result and agent_result.get("action") == "select":
            candidate = await _resolve_inn_candidate(agent_result["inn"])
            if not candidate:
                candidate = _minimal_candidate_from_inn(
                    query,
                    agent_result["inn"],
                    agent_result.get("source") or "yandex_snippets",
                )
            _cache_set(resolve_key, candidate.get("inn") or candidate.get("ogrn") or "", 86400)
            return {
                "status": "resolved",
                "candidate": candidate,
                "source": agent_result.get("source"),
                "sources_status": {
                    "lookup": {
                        "ok": True,
                        "details": agent_result.get("meta"),
                    }
                },
            }
        if agent_result and agent_result.get("action") == "clarify":
            return {
                "status": "clarify",
                "clarify": agent_result.get("clarify"),
                "sources_status": {
                    "lookup": {
                        "ok": False,
                        "details": agent_result.get("meta"),
                    }
                },
            }
        return {"status": "clarify", "clarify": "Could not determine INN from the website. Please utochnite nazvanie or INN."}

    # Name flow: agentic web lookup, then FNS fallback
    search_query = f"{query_norm} официальный сайт ИНН"
    agent_result = await _agentic_web_lookup(
        query_norm,
        search_query,
        session_id,
        telegram_chat_id,
        telegram_tag,
    )
    if agent_result and agent_result.get("action") == "select":
        candidate = await _resolve_inn_candidate(agent_result["inn"])
        if not candidate:
            candidate = _minimal_candidate_from_inn(
                query,
                agent_result["inn"],
                agent_result.get("source") or "yandex_snippets",
            )
        _cache_set(resolve_key, candidate.get("inn") or candidate.get("ogrn") or "", 86400)
        return {
            "status": "resolved",
            "candidate": candidate,
            "source": agent_result.get("source"),
            "sources_status": {
                "lookup": {
                    "ok": True,
                    "details": agent_result.get("meta"),
                }
            },
        }
    if agent_result and agent_result.get("action") == "clarify":
        return {
            "status": "clarify",
            "clarify": agent_result.get("clarify"),
            "sources_status": {
                "lookup": {
                    "ok": False,
                    "details": agent_result.get("meta"),
                }
            },
        }

    # FNS fallback
    rows, err, trace = await _fns_search(query_norm)
    log_session_event(
        session_id,
        telegram_chat_id,
        telegram_tag,
        "fns_name",
        "FNS name results",
        {"query": query_norm},
        {"count": len(rows), "sample": [r.get("name_full") or r.get("name") for r in rows[:3]], "trace": trace},
    )
    if err:
        log_api_error("fns", f"name error: {err}")

    if not rows:
        return {"status": "not_found"}

    query_norm = _normalize_name(query_norm)
    candidates = [
        _build_candidate(r, "fns", 0.7, query_norm) for r in rows[:10]
    ]
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    top = candidates[0]
    log_session_event(
        session_id,
        telegram_chat_id,
        telegram_tag,
        "fns_rank",
        "FNS candidate ranking",
        {"query": query_norm},
        {"top_confidence": top.confidence, "top_name": top.name_full, "total": len(candidates)},
    )

    if top.confidence >= 0.85 and len(candidates) == 1:
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "decision",
            "Single high-confidence FNS match",
            {"query": query_norm},
            {"confidence": top.confidence},
        )
        _cache_set(resolve_key, top.inn or top.ogrn or "", 86400)
        return {"status": "resolved", "candidate": _candidate_to_dict(top), "source": "fns"}

    if len(candidates) <= 3 and 0.6 <= top.confidence < 0.85:
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "decision",
            "Ambiguous 2-3 FNS matches, using DeepSeek",
            {"query": query_norm},
            {"confidence": top.confidence},
        )
        llm_key = _llm_cache_key(query_norm, [_candidate_to_dict(c) for c in candidates])
        llm_cached = _cache_get(llm_key)
        if llm_cached:
            candidate = await _resolve_inn_candidate(llm_cached)
            if candidate:
                return {"status": "resolved", "candidate": candidate, "source": "llm_cache"}
        ds = DeepSeekClient()
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "deepseek_call",
            "DeepSeek disambiguation",
            {"query": query_norm, "candidates": [_candidate_to_dict(c) for c in candidates[:3]]},
            None,
        )
        llm_resp = await ds.resolve(query_norm, [_candidate_to_dict(c) for c in candidates])
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "deepseek_result",
            "DeepSeek response",
            {"query": query_norm},
            llm_resp or {},
        )
        if llm_resp and llm_resp.get("action") == "select" and llm_resp.get("inn"):
            _cache_set(resolve_key, llm_resp["inn"], 86400)
            _cache_set(llm_key, llm_resp["inn"], 86400)
            candidate = await _resolve_inn_candidate(llm_resp["inn"])
            if candidate:
                return {"status": "resolved", "candidate": candidate, "source": "deepseek"}
        if llm_resp and llm_resp.get("action") == "clarify":
            return {"status": "clarify", "clarify": llm_resp.get("clarify")}

    if len(candidates) > 3 or top.confidence < 0.6:
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "decision",
            "Low confidence or many FNS matches, using DeepSeek clarify",
            {"query": query_norm},
            {"confidence": top.confidence, "count": len(candidates)},
        )
        ds = DeepSeekClient()
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "deepseek_call",
            "DeepSeek clarify",
            {"query": query_norm, "candidates": [_candidate_to_dict(c) for c in candidates[:3]]},
            None,
        )
        llm_resp = await ds.resolve(query_norm, [_candidate_to_dict(c) for c in candidates[:3]])
        log_session_event(
            session_id,
            telegram_chat_id,
            telegram_tag,
            "deepseek_result",
            "DeepSeek response",
            {"query": query_norm},
            llm_resp or {},
        )
        if llm_resp and llm_resp.get("action") == "select" and llm_resp.get("inn"):
            _cache_set(resolve_key, llm_resp["inn"], 86400)
            candidate = await _resolve_inn_candidate(llm_resp["inn"])
            if candidate:
                return {"status": "resolved", "candidate": candidate, "source": "deepseek"}
        if llm_resp and llm_resp.get("action") == "clarify":
            return {"status": "clarify", "clarify": llm_resp.get("clarify")}

    return {
        "status": "disambiguate",
        "candidates": [_candidate_to_dict(c) for c in candidates[:5]],
    }
