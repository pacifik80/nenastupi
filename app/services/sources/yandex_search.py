from __future__ import annotations

from typing import List

from yandex_ai_studio_sdk import AIStudio

from app.core.config import settings
from app.services.logging import log_api_error

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 YaBrowser/25.2.0.0 Safari/537.36"
)


class YandexSearchClient:
    def __init__(self):
        self.folder_id = settings.yandex_search_folder_id
        self.api_key = settings.yandex_search_api_key

    def search_web(self, query: str, pages: int = 1, format: str = "xml") -> List[str]:
        results, _ = self.search_web_with_meta(query, pages=pages, format=format)
        return results

    def search_web_with_meta(self, query: str, pages: int = 1, format: str = "xml") -> tuple[List[str], dict]:
        meta = {"query": query, "pages": pages, "format": format}
        if not self.folder_id or not self.api_key:
            meta["status"] = "missing_credentials"
            return [], meta

        try:
            sdk = AIStudio(folder_id=self.folder_id, auth=self.api_key)
            sdk.setup_default_logging("error")
            search = sdk.search_api.web(search_type="ru", user_agent=USER_AGENT)
            results: List[str] = []
            for page in range(max(1, pages)):
                operation = search.run_deferred(query, format=format, page=page)
                search_result = operation.wait(poll_interval=1)
                results.append(search_result.decode("utf-8"))
            meta["status"] = "ok"
            meta["pages_returned"] = len(results)
            meta["bytes"] = sum(len(r.encode("utf-8")) for r in results)
            return results, meta
        except Exception as e:
            log_api_error("yandex_search", f"query={query} error={type(e).__name__}: {e}")
            meta["status"] = "error"
            meta["error"] = type(e).__name__
            return [], meta
