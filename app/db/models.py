from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    ogrn = Column(String(20), unique=True, nullable=False)
    inn = Column(String(20), nullable=True)
    name_full = Column(Text, nullable=False)
    name_short = Column(Text, nullable=True)
    status = Column(String(50), nullable=True)
    reg_date = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Check(Base):
    __tablename__ = "checks"

    id = Column(Integer, primary_key=True)
    query = Column(Text, nullable=False)
    ogrn = Column(String(20), nullable=True)
    channel = Column(String(20), nullable=False, default="web")
    telegram_chat_id = Column(String(50), nullable=True)

    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    report_text = Column(Text, nullable=True)
    risk_json = Column(JSONB, nullable=True)
    sources_json = Column(JSONB, nullable=True)

    success = Column(Boolean, default=False)


class TelegramSession(Base):
    __tablename__ = "telegram_sessions"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100), nullable=True)
    last_query = Column(Text, nullable=True)
    last_result_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiLog(Base):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)
    level = Column(String(20), nullable=False, default="error")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SessionLog(Base):
    __tablename__ = "session_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=True)
    telegram_chat_id = Column(String(50), nullable=True)
    telegram_tag = Column(String(100), nullable=True)
    step = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True)
    response = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
