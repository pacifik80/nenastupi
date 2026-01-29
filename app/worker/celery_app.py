from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "nenastupi",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_routes={
        "app.worker.tasks.*": {"queue": "celery"},
    }
)
