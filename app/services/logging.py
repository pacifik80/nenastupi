from app.db.postgres import SessionLocal
from app.db.models import ApiLog


def log_api_error(source: str, message: str) -> None:
    db = SessionLocal()
    try:
        db.add(ApiLog(source=source, level="error", message=message[:2000]))
        db.commit()
    finally:
        db.close()
