import asyncio
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import get_settings
from app.database import SessionLocal
from app.models.telegram_auth_code import TelegramAuthCode

settings = get_settings()

CODE_EXPIRE_MINUTES = 5

_application: Application | None = None


def _generate_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


async def _start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    telegram_id = update.effective_user.id
    telegram_username = update.effective_user.username

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRE_MINUTES)

    async with SessionLocal() as db:
        await db.execute(
            delete(TelegramAuthCode).where(TelegramAuthCode.telegram_id == telegram_id)
        )
        db.add(
            TelegramAuthCode(
                telegram_id=telegram_id,
                telegram_username=telegram_username,
                code=code,
                expires_at=expires_at,
            )
        )
        await db.commit()

    await update.message.reply_text(
        f"Ваш код для входа: {code}\n\n"
        f"Введите этот код на сайте.\n"
        f"Код действителен {CODE_EXPIRE_MINUTES} минут."
    )


async def start_bot() -> None:
    global _application
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        return

    _application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    _application.add_handler(CommandHandler("start", _start_handler))

    await _application.initialize()
    await _application.start()
    await _application.updater.start_polling(drop_pending_updates=True)
    print("✓ Telegram bot started")


async def stop_bot() -> None:
    global _application
    if _application is None:
        return

    await _application.updater.stop()
    await _application.stop()
    await _application.shutdown()
    _application = None
    print("✓ Telegram bot stopped")
