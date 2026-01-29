import os
import threading
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, text
import redis
from app.core.config import settings
from app.db.postgres import SessionLocal
from app.db.models import Company, TelegramSession, Check, ApiLog, SessionLog
from app.db.neo4j import get_driver

router = APIRouter()
security = HTTPBasic()

templates = Jinja2Templates(directory="app/admin/templates")


def _auth(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != settings.admin_user or credentials.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    tab: str = "status",
    session_id: int | None = None,
    telegram_tag: str | None = None,
    ok: bool = Depends(_auth),
):
    db = SessionLocal()
    try:
        company_count = db.query(func.count(Company.id)).scalar() or 0
        session_count = db.query(func.count(TelegramSession.id)).scalar() or 0
        last_checks = db.query(Check).order_by(Check.requested_at.desc()).limit(10).all()
        last_logs = db.query(ApiLog).order_by(ApiLog.created_at.desc()).limit(20).all()
        session_logs = []
        sessions = []
        if tab == "sessions":
            sessions = db.query(Check).order_by(Check.requested_at.desc()).limit(50).all()
            q = db.query(SessionLog)
            if session_id:
                q = q.filter(SessionLog.session_id == session_id)
            if telegram_tag:
                q = q.filter(SessionLog.telegram_tag.ilike(f"%{telegram_tag}%"))
            session_logs = q.order_by(SessionLog.created_at.desc()).limit(200).all()
    finally:
        db.close()

    infra = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
        "neo4j": _check_neo4j(),
        "celery_queue": _celery_queue_len(),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "company_count": company_count,
            "session_count": session_count,
            "last_checks": last_checks,
            "last_logs": last_logs,
            "infra": infra,
            "session_logs": session_logs,
            "sessions": sessions,
            "tab": tab,
            "filter_session_id": session_id or "",
            "filter_telegram_tag": telegram_tag or "",
        },
    )


@router.post("/admin/restart")
def admin_restart(secret: str = Form(...), ok: bool = Depends(_auth)):
    if secret != settings.restart_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    def _exit():
        os._exit(1)

    threading.Timer(1.0, _exit).start()
    return {"ok": True, "message": "Restarting"}


def _check_postgres():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "fail"
    finally:
        db.close()


def _check_redis():
    try:
        r = redis.Redis.from_url(settings.redis_url)
        r.ping()
        return "ok"
    except Exception:
        return "fail"


def _check_neo4j():
    try:
        driver = get_driver()
        with driver.session() as s:
            s.run("RETURN 1")
        driver.close()
        return "ok"
    except Exception:
        return "fail"


def _celery_queue_len():
    try:
        r = redis.Redis.from_url(settings.redis_url)
        return r.llen("celery")
    except Exception:
        return "n/a"
