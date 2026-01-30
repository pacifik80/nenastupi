import httpx


class FnsError(Exception):
    def __init__(self, code: str, message: str | None = None, trace: list | None = None):
        super().__init__(message or code)
        self.code = code
        self.detail = message or code
        self.trace = trace or []


class FnsClient:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: str):
        rows, _, _ = await self.search_with_status(query)
        return rows

    async def search_with_status(self, query: str):
        try:
            rows, trace = await self._search_with_trace(query)
            return rows, None, trace
        except FnsError as e:
            return [], {"code": e.code, "detail": e.detail}, e.trace

    def _truncate(self, text: str | None, limit: int = 2000) -> str | None:
        if text is None:
            return None
        return text if len(text) <= limit else text[:limit] + "...(truncated)"

    def _trace_add(
        self,
        trace: list,
        method: str,
        url: str,
        status: int | None,
        bytes_len: int | None = None,
        error: str | None = None,
        body: str | None = None,
    ):
        trace.append({
            "method": method,
            "url": url,
            "status": status,
            "bytes": bytes_len,
            "error": error,
            "body": self._truncate(body),
        })

    async def _search_with_trace(self, query: str):
        trace: list = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = None
            try:
                r = await client.post(
                    f"{self.base_url}/",
                    data={"query": query},
                    headers={"User-Agent": "nenastupi/1.0"},
                )
                self._trace_add(trace, "POST", str(r.url), r.status_code, len(r.content or b""), body=r.text)
                if r.status_code in (403, 429):
                    raise FnsError("blocked", f"url={r.url} status={r.status_code}", trace)
                r.raise_for_status()
                data = r.json()
                token = data.get("t")
            except httpx.TimeoutException as e:
                self._trace_add(trace, "POST", f"{self.base_url}/", None, None, f"timeout: {e}")
                raise FnsError("timeout", str(e), trace)
            except httpx.RequestError as e:
                self._trace_add(trace, "POST", f"{self.base_url}/", None, None, f"network: {e}")
                raise FnsError("network", str(e), trace)
            except ValueError as e:
                self._trace_add(trace, "POST", f"{self.base_url}/", r.status_code if "r" in locals() else None, None, f"bad_response: {e}")
                raise FnsError("bad_response", str(e), trace)
            except httpx.HTTPStatusError as e:
                self._trace_add(trace, "POST", f"{self.base_url}/", e.response.status_code if e.response else None, None, f"http_error: {e}")
                raise FnsError("http_error", str(e), trace)
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
                    self._trace_add(trace, "GET", str(resp.url), resp.status_code, len(resp.content or b""), body=resp.text)
                    if resp.status_code in (403, 429):
                        raise FnsError("blocked", f"url={resp.url} status={resp.status_code}", trace)
                    resp.raise_for_status()
                    data = resp.json()
                    rows = data.get("rows") or data.get("items") or []
                    for row in rows:
                        candidates.append(self._normalize(row))
                    if candidates:
                        break
                except httpx.TimeoutException as e:
                    self._trace_add(trace, "GET", url, None, None, f"timeout: {e}")
                    raise FnsError("timeout", str(e), trace)
                except httpx.RequestError as e:
                    self._trace_add(trace, "GET", url, None, None, f"network: {e}")
                    raise FnsError("network", str(e), trace)
                except ValueError as e:
                    self._trace_add(trace, "GET", url, resp.status_code if "resp" in locals() else None, None, f"bad_response: {e}")
                    raise FnsError("bad_response", str(e), trace)
                except httpx.HTTPStatusError as e:
                    self._trace_add(trace, "GET", url, e.response.status_code if e.response else None, None, f"http_error: {e}")
                    raise FnsError("http_error", str(e), trace)
                except FnsError:
                    raise
                except Exception:
                    continue

            return candidates, trace

    def _normalize(self, row: dict):
        return {
            "ogrn": row.get("o") or row.get("ogrn") or row.get("ОГРН"),
            "inn": row.get("i") or row.get("inn") or row.get("ИНН"),
            "name_full": row.get("n") or row.get("name") or row.get("НаимПолн"),
            "name_short": row.get("c") or row.get("short") or row.get("НаимСокр"),
            "status": row.get("s") or row.get("status") or row.get("Статус"),
            "reg_date": row.get("r") or row.get("reg_date") or row.get("ДатаРег"),
        }
