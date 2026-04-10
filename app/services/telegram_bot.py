import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from telegram import Update
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
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


def _show_main_menu_text(user: User) -> str:
    """Build main menu text."""
    return (
        f"👤 Аккаунт: {user.email}\n"
        f"💰 Баланс: {user.balance} ₽\n\n"
        f"Доступные команды:\n"
        f"/devices — Мои устройства\n"
        f"/balance — Проверить баланс\n"
        f"/history — История операций"
    )


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

        backend_url = settings.BACKEND_URL.rstrip("/")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{backend_url}/api/internal/telegram/confirm-link",
                    json={
                        "token": token,
                        "telegram_id": telegram_id,
                        "telegram_username": telegram_username,
                        "telegram_first_name": telegram_first_name,
                    },
                    headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
                )
        except Exception as e:
            print(f"Telegram bot HTTP error: {e}")
            await update.message.reply_text(
                "❌ Ошибка соединения с сервером. Попробуйте позже."
            )
            return

        if response.status_code == 200:
            user_email = response.json()["user_email"]
            # Fetch user to show menu
            user = await _get_user_by_telegram(telegram_id)
            if user:
                await update.message.reply_text(
                    f"✅ Аккаунт успешно привязан!\n\n"
                    f"Email: {user_email}\n\n"
                    f"Теперь вы можете управлять VPN прямо здесь.\n\n"
                    f"{_show_main_menu_text(user)}"
                )
        else:
            error_data = response.json()
            error = error_data.get("detail", "")
            print(f"Telegram link error: status={response.status_code}, body={error_data}")

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
            elif error == "token_not_found":
                await update.message.reply_text(
                    "❌ Токен не найден. Запросите новую ссылку на сайте."
                )
            elif error == "Forbidden":
                await update.message.reply_text(
                    "❌ Ошибка сервера: неверный секретный ключ."
                )
            else:
                await update.message.reply_text(
                    f"❌ Ошибка: {error or 'неизвестная'}. Попробуйте снова."
                )
        return

    # Regular /start — check if user is already linked
    user = await _get_user_by_telegram(telegram_id)
    if user:
        await update.message.reply_text(
            f"👋 Привет, {user.email}!\n\n"
            f"Ваш аккаунт привязан.\n\n"
            f"{_show_main_menu_text(user)}"
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Чтобы привязать аккаунт:\n\n"
            "1. Зайдите на сайт в профиль\n"
            "2. Нажмите «Привязать Telegram»\n"
            "3. Отправьте полученную ссылку сюда"
        )


async def _balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    user = await _get_user_by_telegram(update.effective_user.id)
    if user:
        await update.message.reply_text(f"💰 Ваш баланс: **{user.balance} ₽", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Аккаунт не привязан. Используйте /start для привязки.")


async def _devices_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    user = await _get_user_by_telegram(update.effective_user.id)
    if user:
        async with SessionLocal() as db:
            from app.crud.spa import list_devices
            devices = await list_devices(db, user)
            if devices:
                msg = "📱 Ваши устройства:\n\n" + "\n".join(
                    f"• {d.name} ({d.type}) — {d.status}" for d in devices
                )
            else:
                msg = "📱 У вас пока нет устройств."
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("❌ Аккаунт не привязан. Используйте /start для привязки.")


async def _history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    user = await _get_user_by_telegram(update.effective_user.id)
    if user:
        async with SessionLocal() as db:
            from app.crud.spa import list_transactions
            txs = await list_transactions(db, user)
            if txs:
                msg = "📊 Последние операции:\n\n" + "\n".join(
                    f"• {tx.created_at.strftime('%d.%m.%Y') if tx.created_at else '??.??.????'}: {tx.type} — {tx.amount} ₽ ({tx.description})" for tx in txs[:10]
                )
            else:
                msg = "📊 Операций пока нет."
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("❌ Аккаунт не привязан. Используйте /start для привязки.")


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
        f"Доступные команды:\n"
        f"/devices — Мои устройства\n"
        f"/balance — Проверить баланс\n"
        f"/history — История операций"
    )


async def start_bot() -> None:
    global _application
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        return

    try:
        _application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        _application.add_handler(CommandHandler("start", _start_handler))
        _application.add_handler(CommandHandler("balance", _balance_handler))
        _application.add_handler(CommandHandler("devices", _devices_handler))
        _application.add_handler(CommandHandler("history", _history_handler))
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
