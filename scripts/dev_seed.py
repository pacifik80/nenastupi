from app.db.postgres import SessionLocal
from app.db.models import Company
from app.services.demo_data import DEMO_COMPANIES


def main():
    db = SessionLocal()
    try:
        for c in DEMO_COMPANIES:
            existing = db.query(Company).filter(Company.ogrn == c["ogrn"]).first()
            if existing:
                continue
            db.add(Company(
                ogrn=c["ogrn"],
                inn=c["inn"],
                name_full=c["name_full"],
                name_short=c["name_short"],
                status=c["status"],
                reg_date=c["reg_date"],
            ))
        db.commit()
        print("Seeded demo companies")
    finally:
        db.close()


if __name__ == "__main__":
    main()
