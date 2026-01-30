from sqlalchemy import text
from app.db.postgres import engine
from app.db.models import Base


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'session_logs' AND column_name = 'response'
                    ) THEN
                        ALTER TABLE session_logs ADD COLUMN response JSONB;
                    END IF;
                END $$;
                """
            )
        )
