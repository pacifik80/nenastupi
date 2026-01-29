from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.orchestrator import check_company
from app.db.postgres import SessionLocal
from app.db.models import Check, Company

router = APIRouter()


class CheckRequest(BaseModel):
    query: str
    channel: str | None = "web"
    telegram_chat_id: str | None = None


@router.post("/check")
async def check(req: CheckRequest):
    result = await check_company(req.query)

    db = SessionLocal()
    try:
        if result.get("ok"):
            company = result.get("company") or {}
            if company.get("ogrn"):
                existing = db.query(Company).filter(Company.ogrn == company["ogrn"]).first()
                if not existing:
                    db.add(Company(
                        ogrn=company.get("ogrn"),
                        inn=company.get("inn"),
                        name_full=company.get("name_full") or company.get("name_short") or "Unknown",
                        name_short=company.get("name_short"),
                        status=company.get("status"),
                        reg_date=company.get("reg_date"),
                    ))

            db.add(Check(
                query=req.query,
                ogrn=company.get("ogrn"),
                channel=req.channel or "web",
                telegram_chat_id=req.telegram_chat_id,
                completed_at=datetime.utcnow(),
                report_text=result.get("report"),
                risk_json=result.get("risks"),
                sources_json={
                    "bankruptcy": result.get("bankruptcy"),
                    "news": result.get("news"),
                },
                success=True,
            ))
        else:
            db.add(Check(
                query=req.query,
                channel=req.channel or "web",
                telegram_chat_id=req.telegram_chat_id,
                completed_at=datetime.utcnow(),
                success=False,
            ))
        db.commit()
    finally:
        db.close()

    return result
