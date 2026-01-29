import json
import hashlib
from app.core.config import settings
import redis


_client = None


def get_client():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def make_key(query: str) -> str:
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"check:{h}"


def get_cached(query: str):
    key = make_key(query)
    data = get_client().get(key)
    if not data:
        return None
    return json.loads(data)


def set_cached(query: str, payload: dict, ttl: int = 86400):
    key = make_key(query)
    get_client().setex(key, ttl, json.dumps(payload, ensure_ascii=False))
