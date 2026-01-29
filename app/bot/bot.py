import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from app.core.config import settings
from app.services.orchestrator import check_company
from app.db.postgres import SessionLocal
from app.db.models import TelegramSession


def _upsert_session(chat_id: str, username: str | None, last_query: str | None):
    db = SessionLocal()
    try:
        session = db.query(TelegramSession).filter(TelegramSession.chat_id == str(chat_id)).first()
        if not session:
            session = TelegramSession(chat_id=str(chat_id), username=username)
            db.add(session)
        session.last_query = last_query
        session.last_result_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


async def handle_start(message: types.Message):
    await message.answer("Введите название компании, ИНН или ОГРН.")

async def handle_query(message: types.Message):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите название компании, ИНН или ОГРН.")
        return

    result = await check_company(query)
    if result.get("ok"):
        await message.answer(result.get("report"))
    else:
        await message.answer("Компания не найдена. Проверьте запрос.")

    _upsert_session(str(message.chat.id), message.from_user.username, query)


async def main():
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    dp.message.register(handle_start, CommandStart())
    dp.message.register(handle_query)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
