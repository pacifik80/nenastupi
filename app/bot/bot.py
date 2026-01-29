import asyncio
import time
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.config import settings
from app.db.models import TelegramSession, Check
from app.db.postgres import SessionLocal
from app.services.demo_data import find_demo_company
from app.services.lookup import lookup_company
from app.services.report import build_report
from app.services.risk import calculate_risks
from app.services.sources.efrsb import EfrsbClient
from app.services.sources.news import NewsClient
from app.services.session_log import log_session_event

WELCOME_TEXT = """
🔍 <b>РаботоФонарь</b> — проверка работодателя

Что я умею:
✅ Проверить компанию по названию или ИНН/ОГРН
✅ Найти признаки банкротства
✅ Собрать свежие новости о работодателе

⚠️ Важно: сервис использует открытые данные.
Результат — ориентир, а не юридическая гарантия.

👉 Введите название компании или ИНН/ОГРН:
""".strip()

HOW_IT_WORKS_TEXT = (
    "Коротко: бот собирает данные из открытых источников и показывает риски.\n"
    "Подробнее на сайте: https://nenastupi.ru"
)

DISCLAIMER_TEXT = (
    "⚠️ Данные актуальны на дату запроса. "
    "Сервис не даёт юридических гарантий."
)

SOURCES_TEXT = "ℹ️ Источники: ФНС (ЕГРЮЛ), ЕФРСБ, Google News RSS"


class UserState(StatesGroup):
    awaiting_selection = State()


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


def _create_check(query: str, chat_id: str, telegram_tag: str | None) -> int:
    db = SessionLocal()
    try:
        check = Check(
            query=query,
            channel="telegram",
            telegram_chat_id=chat_id,
        )
        db.add(check)
        db.commit()
        db.refresh(check)
        return check.id
    finally:
        db.close()


def _mark_check(check_id: int | None, success: bool) -> None:
    if check_id is None:
        return
    db = SessionLocal()
    try:
        check = db.query(Check).filter(Check.id == check_id).first()
        if check:
            check.success = success
            check.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


class ProgressMessage:
    def __init__(self, bot: Bot, chat_id: int, company_name: str):
        self.bot = bot
        self.chat_id = chat_id
        self.company_name = company_name
        self.message_id: Optional[int] = None
        self._last_update = 0.0

    async def show(self):
        text = self._build_progress_text(0, "Инициализация...")
        msg = await self.bot.send_message(self.chat_id, text, parse_mode="HTML")
        self.message_id = msg.message_id

    async def update(self, percent: int, status: str):
        if self.message_id is None:
            return
        now = time.time()
        if now - self._last_update < 1.0:
            await asyncio.sleep(1.0 - (now - self._last_update))
        text = self._build_progress_text(percent, status)
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode="HTML",
            )
            self._last_update = time.time()
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise

    async def complete(self, final_text: str, reply_markup=None):
        if self.message_id is None:
            await self.bot.send_message(self.chat_id, final_text, parse_mode="HTML", reply_markup=reply_markup)
            return
        if len(final_text) > 4096:
            final_text = final_text[:4090] + " [...]"
        await self.bot.edit_message_text(
            chat_id=self.chat_id,
            message_id=self.message_id,
            text=final_text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    def _build_progress_text(self, percent: int, status: str) -> str:
        filled = "▰" * (percent // 10)
        empty = "▱" * (10 - percent // 10)
        return (
            f"🔍 Проверяю компанию «{self.company_name}»...\n\n"
            f"<code>{filled}{empty}</code> {percent}% — {status}"
        )


def _build_final_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Проверить ещё", callback_data="restart")
    kb.button(text="ℹ️ Как это работает", callback_data="how_it_works")
    kb.adjust(2)
    return kb.as_markup()


async def _resolve_candidates(query: str, session_id: int | None, telegram_chat_id: str | None, telegram_tag: str | None):
    payload = await lookup_company(
        query,
        session_id=session_id,
        telegram_chat_id=telegram_chat_id,
        telegram_tag=telegram_tag,
    )
    return payload.get("candidates", []), payload.get("fns_error")


async def _start_checking(message: types.Message, company: dict, query: str, session_id: int | None):
    progress = ProgressMessage(
        bot=message.bot,
        chat_id=message.chat.id,
        company_name=company.get("name_short") or company.get("name_full") or query,
    )
    await progress.show()

    try:
        await progress.update(20, "Запрос к ФНС...")
        log_session_event(session_id, str(message.chat.id), message.from_user.username, "check_start", "Started checks", {"query": query})

        efrsb = EfrsbClient(settings.efrsb_base_url, settings.request_timeout)
        await progress.update(55, "Проверка ЕФРСБ...")
        bankruptcy = await efrsb.check_bankruptcy(company.get("inn") or company.get("ogrn"))
        log_session_event(session_id, str(message.chat.id), message.from_user.username, "check_efrsb", "EFRSB response", bankruptcy)

        news = NewsClient(settings.request_timeout)
        await progress.update(80, "Сбор новостей за 90 дней...")
        news_items = await news.search_google_rss(company.get("name_short") or company.get("name_full"))
        log_session_event(session_id, str(message.chat.id), message.from_user.username, "check_news", "News response", {"count": len(news_items)})

        risks = calculate_risks(company, bankruptcy, news_items)
        await progress.update(95, "Формирование отчёта...")

        report = build_report(company, risks, news_items)
        final_text = "\n\n".join([report, SOURCES_TEXT, DISCLAIMER_TEXT])
        await progress.complete(final_text, reply_markup=_build_final_keyboard())
        log_session_event(session_id, str(message.chat.id), message.from_user.username, "check_done", "Report sent", {"risk_count": len(risks)})
        _mark_check(session_id, True)

        _upsert_session(str(message.chat.id), message.from_user.username, query)
    except Exception as e:
        error_text = (
            "❌ Ошибка при проверке компании.\n\n"
            f"Причина: {str(e)[:120]}\n\n"
            "Попробуйте позже или проверьте другую компанию."
        )
        await progress.complete(error_text, reply_markup=_build_final_keyboard())
        log_session_event(session_id, str(message.chat.id), message.from_user.username, "check_error", str(e), None)
        _mark_check(session_id, False)


async def handle_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME_TEXT, parse_mode="HTML")


async def handle_query(message: types.Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите название компании, ИНН или ОГРН.")
        return

    telegram_tag = message.from_user.username
    session_id = _create_check(query, str(message.chat.id), telegram_tag)
    log_session_event(session_id, str(message.chat.id), telegram_tag, "query_received", "User query received", {"query": query})

    candidates, err = await _resolve_candidates(query, session_id, str(message.chat.id), telegram_tag)
    err_code = err.get("code") if isinstance(err, dict) else err
    if err_code == "blocked" and not candidates:
        await message.answer("⚠️ ФНС временно недоступен. Попробуйте позже.")
        return
    if err and not candidates:
        await message.answer("⚠️ Временная ошибка при обращении к ФНС. Попробуйте позже.")
        return

    if not candidates and settings.allow_demo_fallback:
        demo = find_demo_company(query)
        if demo:
            await _start_checking(message, demo, query, session_id)
            return

    if len(candidates) == 0:
        await message.answer("❌ Не найдено компаний по запросу. Проверьте написание или попробуйте ИНН/ОГРН.")
        return

    if len(candidates) == 1:
        await _start_checking(message, candidates[0], query, session_id)
        return
    if candidates and candidates[0].get("confidence", 0) >= 0.85 and len(candidates[0].get("sources", [])) >= 2:
        await _start_checking(message, candidates[0], query, session_id)
        return

    kb = InlineKeyboardBuilder()
    text_lines = ["Найдено несколько компаний. Выберите нужную:"]
    for i, comp in enumerate(candidates[:5], 1):
        name = comp.get("name_short") or comp.get("name_full") or "Компания"
        inn = comp.get("inn") or "-"
        kb.button(text=f"{i}️⃣ {name} (ИНН {inn[:6]}...)", callback_data=f"select:{i}")
        status = comp.get("status") or "неизвестно"
        text_lines.append(f"{i}. {name} (ИНН {inn}, статус: {status})")
    kb.adjust(1)

    await message.answer("\n".join(text_lines), reply_markup=kb.as_markup())
    log_session_event(session_id, str(message.chat.id), telegram_tag, "disambiguation", "Multiple candidates shown", {"count": len(candidates)})
    await state.update_data(candidates=candidates, query=query)
    await state.update_data(session_id=session_id)
    await state.set_state(UserState.awaiting_selection)


async def handle_selection(callback: types.CallbackQuery, state: FSMContext):
    if not callback.data or not callback.data.startswith("select:"):
        return
    idx = callback.data.split(":", 1)[1]
    data = await state.get_data()
    candidates = data.get("candidates", [])
    query = data.get("query", "")
    session_id = data.get("session_id")
    await state.clear()

    try:
        company = candidates[int(idx) - 1]
    except Exception:
        company = None
    if not company:
        await callback.answer("Не удалось найти компанию, попробуйте снова.", show_alert=True)
        return

    await callback.answer()
    log_session_event(
        session_id,
        str(callback.message.chat.id),
        callback.from_user.username,
        "selection",
        "User selected candidate",
        {"ogrn": company.get("ogrn"), "inn": company.get("inn")},
    )
    await _start_checking(callback.message, company, query, session_id)


async def handle_restart(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.answer("Введите название компании, ИНН или ОГРН.")


async def handle_how_it_works(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(HOW_IT_WORKS_TEXT)


async def main():
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(handle_start, CommandStart())
    dp.message.register(handle_query)

    dp.callback_query.register(handle_selection, F.data.startswith("select:"))
    dp.callback_query.register(handle_restart, F.data == "restart")
    dp.callback_query.register(handle_how_it_works, F.data == "how_it_works")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
