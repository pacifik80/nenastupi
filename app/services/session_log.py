from app.db.postgres import SessionLocal
from app.db.models import SessionLog


def log_session_event(
    session_id: int | None,
    telegram_chat_id: str | None,
    telegram_tag: str | None,
    step: str,
    message: str,
    payload: dict | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            SessionLog(
                session_id=session_id,
                telegram_chat_id=telegram_chat_id,
                telegram_tag=telegram_tag,
                step=step,
                message=message[:2000],
                payload=payload,
            )
        )
        db.commit()
    finally:
        db.close()
