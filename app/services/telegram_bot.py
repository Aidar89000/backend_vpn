import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import get_settings
from app.database import SessionLocal
from app.models.telegram_auth_code import TelegramAuthCode
from app.models.user import User

settings = get_settings()

CODE_EXPIRE_MINUTES = 5
_application: Application | None = None


def _generate_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


async def _get_user_by_telegram(telegram_id: int) -> User | None:
    """Find user by Telegram ID."""
    async with SessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


def _build_main_menu() -> InlineKeyboardMarkup:
    """Build main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📱 Мои устройства", callback_data="devices")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📊 История", callback_data="history")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def _start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    args = context.args
    telegram_id = update.effective_user.id
    telegram_username = update.effective_user.username
    telegram_first_name = update.effective_user.first_name

    # /start with token — account linking
    if args and len(args) >= 1:
        token = args[0]

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{settings.REPO_DIR}/api/internal/telegram/confirm-link",
                    json={
                        "token": token,
                        "telegram_id": telegram_id,
                        "telegram_username": telegram_username,
                        "telegram_first_name": telegram_first_name,
                    },
                    headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
                )
            except Exception:
                # Try localhost URL for development
                try:
                    response = await client.post(
                        "http://localhost:8000/api/internal/telegram/confirm-link",
                        json={
                            "token": token,
                            "telegram_id": telegram_id,
                            "telegram_username": telegram_username,
                            "telegram_first_name": telegram_first_name,
                        },
                        headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
                    )
                except Exception:
                    await update.message.reply_text(
                        "❌ Ошибка соединения с сервером. Попробуйте позже."
                    )
                    return

        if response.status_code == 200:
            user_email = response.json()["user_email"]
            await update.message.reply_text(
                f"✅ Аккаунт успешно привязан!\n\n"
                f"Email: {user_email}\n\n"
                f"Теперь вы можете управлять VPN прямо здесь.",
                reply_markup=_build_main_menu(),
            )
        else:
            error_data = response.json()
            error = error_data.get("detail", "")

            if error == "token_expired":
                await update.message.reply_text(
                    "❌ Ссылка устарела. Вернитесь на сайт и запросите новую."
                )
            elif error == "token_used":
                await update.message.reply_text(
                    "❌ Ссылка уже была использована."
                )
            elif error == "telegram_already_linked":
                await update.message.reply_text(
                    "⚠️ Этот Telegram уже привязан к другому аккаунту."
                )
            else:
                await update.message.reply_text(
                    "❌ Что-то пошло не так. Попробуйте снова."
                )
        return

    # Regular /start — check if user is already linked
    user = await _get_user_by_telegram(telegram_id)
    if user:
        await update.message.reply_text(
            f"👋 Привет, {user.email}!\n\n"
            f"Ваш аккаунт привязан. Чем могу помочь?",
            reply_markup=_build_main_menu(),
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Чтобы привязать аккаунт:\n\n"
            "1. Зайдите на сайт в профиль\n"
            "2. Нажмите «Привязать Telegram»\n"
            "3. Отправьте полученную ссылку сюда"
        )


async def _message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any message — check if user is linked."""
    if not update.effective_user or not update.message:
        return

    telegram_id = update.effective_user.id
    user = await _get_user_by_telegram(telegram_id)

    if not user:
        return  # Don't respond to unlinked users

    # User is linked — show their info
    await update.message.reply_text(
        f"👤 Аккаунт: {user.email}\n"
        f"💰 Баланс: {user.balance} ₽\n\n"
        f"Используйте меню для управления.",
        reply_markup=_build_main_menu(),
    )


async def start_bot() -> None:
    global _application
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        return

    try:
        _application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        _application.add_handler(CommandHandler("start", _start_handler))
        _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _message_handler))

        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling(drop_pending_updates=True)
        print("✓ Telegram bot started")
    except Exception as exc:
        # Не блокируем запуск приложения при ошибках Telegram бота
        print(f"⚠ Telegram bot failed to start: {exc}")
        print("Application will continue running without Telegram authentication")
        _application = None


async def stop_bot() -> None:
    global _application
    if _application is None:
        return

    await _application.updater.stop()
    await _application.stop()
    await _application.shutdown()
    _application = None
    print("✓ Telegram bot stopped")
