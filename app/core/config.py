from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    admin_user: str = "admin"
    admin_password: str = "change_me"
    restart_secret: str = "change_me"

    postgres_dsn: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/nenastupi"
    redis_url: str = "redis://redis:6379/0"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "dev_password"

    telegram_bot_token: str = ""

    allow_demo_fallback: bool = True
    news_source: str = "google_rss"
    request_timeout: int = 10

    fns_base_url: str = "https://egrul.nalog.ru"
    efrsb_base_url: str = "https://bankrot.fedresurs.ru"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
