# Decisions Log

This log captures key implementation decisions. It can be updated or amended later.

## 2026-01-29

- **Stack**: Python 3.11 + FastAPI for API/admin; Celery + Redis for background tasks; PostgreSQL for relational data; Neo4j for graph relations; Docker Compose for local dev.
- **API style**: REST (OpenAPI via FastAPI).
- **MVP data sources**: FNS (EGRUL), EFRSB (minimal parser), Google News RSS (no bypass).
- **Legal constraints**: no Cloudflare/robots/ToS bypass; only allowed sources.
- **Telegram bot**: aiogram, polling for MVP.
- **LLM/NLP**: disabled for MVP; deterministic logic + keywords; LLM integration deferred.
- **Admin console**: minimal panel for infra status, company count, Telegram sessions, last checks; API restart action.
- **Local secrets**: store in `.env` and local `scripts/local_env.ps1`, exclude from git.
- **Telegram dialog (MVP)**: /start with welcome + disclaimer; disambiguation list (2-5) when multiple matches; progress via editing a single message (<= 1 update/sec) with real steps FNS -> EFRSB -> News -> Report; buttons "Check again" and "How it works" (short text + https://nenastupi.ru).
- **FNS retries**: retry only for soft errors (timeout/network/bad_response/http_error); do not retry on blocked/429.
- **Entity lookup**: multi-source parallel lookup (FNS, Kontur, hh.ru, RusProfile, Zakupki, KAD, EFRSB where applicable) with normalization and consensus scoring before disambiguation.
- **Lookup cache**: cache lookup results in Redis for 24 hours to avoid repeated scans of sources.
- **HTML sources**: add >=2s delay per request for RusProfile/Zakupki to respect robots and reduce blocking risk.
- **Lookup strategy v2**: cascade rules -> cache -> FNS search -> Yandex search (snippet INN extraction) -> DeepSeek disambiguation only when needed; LLM is last resort.

