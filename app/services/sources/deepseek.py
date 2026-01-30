from __future__ import annotations

import json
import time
from typing import Optional

import httpx

from app.core.config import settings
from app.services.logging import log_api_error


class DeepSeekClient:
    def __init__(self):
        self.api_base = settings.deepseek_api_base.rstrip("/")
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_base and self.model)

    def build_web_prompt(
        self,
        query: str,
        search_query: str,
        snippets: list[str],
        step: int,
        max_steps: int,
    ) -> str:
        return self._build_web_prompt(query, search_query, snippets, step, max_steps)

    async def resolve(self, query: str, candidates: list[dict]) -> dict | None:
        if not self.is_configured():
            return None

        prompt = self._build_prompt(query, candidates)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert on Russian companies. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.api_base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    log_api_error("deepseek", f"url={url} status={resp.status_code} body={resp.text[:500]}")
                    return None
                data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._parse_json(text)
        except Exception as e:
            log_api_error("deepseek", f"url={url} error={type(e).__name__}: {e}")
            return None

    async def think_web(
        self,
        query: str,
        search_query: str,
        snippets: list[str],
        step: int,
        max_steps: int,
    ) -> dict | None:
        if not self.is_configured():
            return None

        prompt = self.build_web_prompt(query, search_query, snippets, step, max_steps)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a careful analyst. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.api_base}/chat/completions"
        try:
            started = time.monotonic()
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    log_api_error("deepseek", f"url={url} status={resp.status_code} body={resp.text[:500]}")
                    return None
                data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._parse_json(text)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if parsed is None:
                return {
                    "_ok": False,
                    "_parse_error": True,
                    "_raw": text,
                    "_http_status": resp.status_code,
                    "_latency_ms": elapsed_ms,
                    "_model": self.model,
                }
            parsed["_ok"] = True
            parsed["_raw"] = text
            parsed["_http_status"] = resp.status_code
            parsed["_latency_ms"] = elapsed_ms
            parsed["_model"] = self.model
            return parsed
        except Exception as e:
            log_api_error("deepseek", f"url={url} error={type(e).__name__}: {e}")
            return None

    async def generate_news_queries(self, company: str) -> list[str] | None:
        if not self.is_configured():
            return None

        prompt = self._build_news_prompt(company)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a Russian news analyst. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.api_base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    log_api_error("deepseek", f"url={url} status={resp.status_code} body={resp.text[:500]}")
                    return None
                data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._parse_json(text) or {}
            queries = parsed.get("queries") if isinstance(parsed, dict) else None
            if isinstance(queries, list):
                return [q.strip() for q in queries if isinstance(q, str) and q.strip()]
            return None
        except Exception as e:
            log_api_error("deepseek", f"url={url} error={type(e).__name__}: {e}")
            return None

    async def rank_employer_news(self, company: str, items: list[dict], max_items: int = 5) -> list[dict] | None:
        if not self.is_configured():
            return None
        if not items:
            return []

        prompt = self._build_news_rank_prompt(company, items, max_items=max_items)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a Russian analyst. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.api_base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    log_api_error("deepseek", f"url={url} status={resp.status_code} body={resp.text[:500]}")
                    return None
                data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._parse_json(text) or {}
            selected = parsed.get("selected") if isinstance(parsed, dict) else None
            if not isinstance(selected, list):
                return None
            results = []
            for row in selected:
                if not isinstance(row, dict):
                    continue
                idx = row.get("id")
                reason = row.get("reason")
                if isinstance(idx, int) and 0 <= idx < len(items):
                    item = dict(items[idx])
                    if isinstance(reason, str) and reason.strip():
                        item["reason"] = reason.strip()
                    results.append(item)
            return results[:max_items]
        except Exception as e:
            log_api_error("deepseek", f"url={url} error={type(e).__name__}: {e}")
            return None

    def _build_prompt(self, query: str, candidates: list[dict]) -> str:
        lines = [
            f'Query: "{query}"',
            "",
            "Registry options:",
        ]
        for i, c in enumerate(candidates[:3], 1):
            name = c.get("name_full") or c.get("name_short") or ""
            inn = c.get("inn") or "-"
            region = c.get("region") or "-"
            lines.append(f'{i}. "{name}" (INN {inn}, {region})')
        lines.append("")
        lines.append("Rules:")
        lines.append("- If one option is clearly correct, return its INN")
        lines.append("- If options are ambiguous, ask one clarification question")
        lines.append("- Reply strictly in JSON, no extra text")
        lines.append("")
        lines.append("Format:")
        lines.append('{"action":"select|clarify","inn":"string or null","clarify":"question or null"}')
        return "\n".join(lines)

    def _parse_json(self, text: str) -> Optional[dict]:
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None

    def _build_web_prompt(
        self,
        query: str,
        search_query: str,
        snippets: list[str],
        step: int,
        max_steps: int,
    ) -> str:
        lines = [
            f'User query: "{query}"',
            f'Search query: "{search_query}"',
            f"Step: {step}/{max_steps}",
            "",
            "Snippets:",
        ]
        for i, s in enumerate(snippets[:8], 1):
            lines.append(f"{i}. {s}")
        lines.append("")
        lines.append("Rules:")
        lines.append("- If you can identify a single correct company, return its INN/OGRN")
        lines.append("- If ambiguous, ask ONE clarifying question")
        lines.append("- If you need a better search, return a refined search_query")
        lines.append("- Reply strictly in JSON, no extra text")
        lines.append("")
        lines.append("Format:")
        lines.append('{"action":"select|clarify|search","inn":"string or null","clarify":"question or null","search_query":"string or null"}')
        return "\n".join(lines)

    def _build_news_prompt(self, company: str) -> str:
        lines = [
            f'Company: "{company}"',
            "",
            "Task: Suggest 3-5 Russian Google News queries to find only employer-relevant news.",
            "Focus on:",
            "- кадровые изменения, назначения/увольнения руководства",
            "- сокращения, найм, открытие/закрытие направлений",
            "- суды, банкротства, штрафы, мошенничество, проверки",
            "",
            "Rules:",
            "- Use OR operators and quoted company name",
            "- Reply strictly in JSON, no extra text",
            "",
            "Format:",
            '{"queries":["...","..."]}',
        ]
        return "\n".join(lines)

    def _build_news_rank_prompt(self, company: str, items: list[dict], max_items: int) -> str:
        lines = [
            f'Company: "{company}"',
            f"Max items: {max_items}",
            "",
            "Task: Select only articles that materially affect employer reputation.",
            "Include кадровые изменения, сокращения/найм, суды, банкротства, штрафы, мошенничество, проверки.",
            "Exclude marketing, entertainment, unrelated news.",
            "",
            "Articles:",
        ]
        for i, item in enumerate(items):
            title = item.get("title") or ""
            summary = item.get("summary") or ""
            source = item.get("source") or ""
            lines.append(f"{i}. {title} | {source} | {summary}")
        lines.append("")
        lines.append("Rules:")
        lines.append("- Return only ids of relevant articles")
        lines.append("- Provide 1-sentence reason for relevance")
        lines.append("- Reply strictly in JSON, no extra text")
        lines.append("")
        lines.append("Format:")
        lines.append('{"selected":[{"id":0,"reason":"..."}, {"id":1,"reason":"..."}]}')
        return "\n".join(lines)
