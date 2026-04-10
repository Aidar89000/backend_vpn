import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from app.config import get_settings
from app.database import SessionLocal
from app.models.telegram_auth_code import TelegramAuthCode
from app.models.user import User

settings = get_settings()

# Conversation states
WAITING_DEVICE_NAME = 1
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


def _build_main_menu() -> InlineKeyboardMarkup:
    """Build main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📱 Мои устройства", callback_data="devices")],
        [InlineKeyboardButton("➕ Добавить устройство", callback_data="add_device")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📊 История", callback_data="history")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_device_keyboard(device_id: int) -> InlineKeyboardMarkup:
    """Build device action keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить ключ", callback_data=f"refresh:{device_id}")],
        [InlineKeyboardButton("🗑 Удалить устройство", callback_data=f"delete_confirm:{device_id}")],
        [InlineKeyboardButton("◀ Назад", callback_data="devices")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_delete_keyboard(device_id: int) -> InlineKeyboardMarkup:
    """Build delete confirmation keyboard."""
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete:{device_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"device:{device_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_add_type_keyboard() -> InlineKeyboardMarkup:
    """Build device type selection keyboard."""
    keyboard = [
        [InlineKeyboardButton("🍎 iOS", callback_data="add_type:ios")],
        [InlineKeyboardButton("🤖 Android", callback_data="add_type:android")],
        [InlineKeyboardButton("💻 PC", callback_data="add_type:pc")],
        [InlineKeyboardButton("◀ Отмена", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_history_keyboard() -> InlineKeyboardMarkup:
    """Build history back keyboard."""
    keyboard = [
        [InlineKeyboardButton("◀ Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def _show_devices_message(query_or_update, user) -> None:
    """Show devices list with inline keyboard."""
    async with SessionLocal() as db:
        from app.crud.spa import list_devices
        devices = await list_devices(db, user)

    if not devices:
        keyboard = [
            [InlineKeyboardButton("➕ Добавить устройство", callback_data="add_device")],
            [InlineKeyboardButton("◀ Назад", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "📱 У вас пока нет устройств."
    else:
        keyboard = []
        for d in devices:
            status_icon = "✅" if d.status == "active" else "⏸"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} {d.name} ({d.device_type})",
                    callback_data=f"device:{d.id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("◀ Назад", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "📱 Ваши устройства. Выберите для просмотра ключа:"

    if hasattr(query_or_update, "edit_message_text"):
        await query_or_update.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query_or_update.reply_text(text, reply_markup=reply_markup)


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
            await update.message.reply_text("❌ Ошибка соединения с сервером. Попробуйте позже.")
            return

        if response.status_code == 200:
            user_email = response.json()["user_email"]
            user = await _get_user_by_telegram(telegram_id)
            if user:
                await update.message.reply_text(
                    f"✅ Аккаунт успешно привязан!\n\n"
                    f"Email: {user_email}\n\n"
                    f"Теперь вы можете управлять VPN прямо здесь.",
                    reply_markup=_build_main_menu()
                )
        else:
            error_data = response.json()
            error = error_data.get("detail", "")
            print(f"Telegram link error: status={response.status_code}, body={error_data}")

            if error == "token_expired":
                await update.message.reply_text("❌ Ссылка устарела. Вернитесь на сайт и запросите новую.")
            elif error == "token_used":
                await update.message.reply_text("❌ Ссылка уже была использована.")
            elif error == "telegram_already_linked":
                await update.message.reply_text("⚠️ Этот Telegram уже привязан к другому аккаунту.")
            elif error == "token_not_found":
                await update.message.reply_text("❌ Токен не найден. Запросите новую ссылку на сайте.")
            elif error == "Forbidden":
                await update.message.reply_text("❌ Ошибка сервера: неверный секретный ключ.")
            else:
                await update.message.reply_text(f"❌ Ошибка: {error or 'неизвестная'}. Попробуйте снова.")
        return

    # Regular /start
    user = await _get_user_by_telegram(telegram_id)
    if user:
        await update.message.reply_text(
            f"👋 Привет, {user.email}!\n\n"
            f"Выберите действие:",
            reply_markup=_build_main_menu()
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Чтобы привязать аккаунт:\n\n"
            "1. Зайдите на сайт в профиль\n"
            "2. Нажмите «Привязать Telegram»\n"
            "3. Отправьте полученную ссылку сюда"
        )


async def _device_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all inline button callbacks."""
    query = update.callback_query
    if not query:
        return

    await query.answer()

    user = await _get_user_by_telegram(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Аккаунт не привязан. Используйте /start для привязки.")
        return

    data = query.data

    # === Main Menu ===
    if data == "main_menu":
        await query.edit_message_text("Выберите действие:", reply_markup=_build_main_menu())
        return

    # === Balance ===
    if data == "balance":
        keyboard = [[InlineKeyboardButton("◀ Назад", callback_data="main_menu")]]
        await query.edit_message_text(
            f"💰 Ваш баланс: **{user.balance} ₽",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # === History ===
    if data == "history":
        async with SessionLocal() as db:
            from app.crud.spa import list_transactions
            txs = await list_transactions(db, user)

        if txs:
            msg = "📊 Последние операции:\n\n" + "\n".join(
                f"• {tx.created_at.strftime('%d.%m.%Y') if tx.created_at else '??.??.????'}: {tx.type} — {tx.amount} ₽ ({tx.description})"
                for tx in txs[:10]
            )
        else:
            msg = "📊 Операций пока нет."

        await query.edit_message_text(msg, reply_markup=_build_history_keyboard())
        return

    # === Devices List ===
    if data == "devices":
        await _show_devices_message(query, user)
        return

    # === Add Device — Type Selection ===
    if data == "add_device":
        await query.edit_message_text(
            "➕ Добавление устройства\n\n"
            "Стоимость: 100 ₽ за каждое устройство.\n\n"
            "Выберите тип устройства:",
            reply_markup=_build_add_type_keyboard()
        )
        return

    # === Add Device — Type Selected, wait for name ===
    if data.startswith("add_type:"):
        device_type = data.split(":", 1)[1]
        context.user_data["add_device_type"] = device_type

        type_labels = {"ios": "🍎 iOS", "android": "🤖 Android", "pc": "💻 PC"}
        await query.edit_message_text(
            f"➕ Добавление устройства\n\n"
            f"Тип: {type_labels.get(device_type, device_type)}\n\n"
            f"Введите название устройства (например, iPhone, Pixel, Windows PC):"
        )
        return

    # === Device Selected ===
    if data.startswith("device:"):
        device_id = int(data.split(":", 1)[1])

        async with SessionLocal() as db:
            from app.crud.spa import list_devices
            devices = await list_devices(db, user)

        device = next((d for d in devices if d.id == device_id), None)
        if not device:
            await query.edit_message_text("❌ Устройство не найдено.")
            return

        display_key = device.connection_key if len(device.connection_key) <= 400 else device.connection_key[:400] + "..."

        await query.edit_message_text(
            f"📱 *{device.name}* ({device.device_type})\n"
            f"Статус: {device.status}\n\n"
            f"🔑 Ваш VPN ключ:\n\n"
            f"`{display_key}`\n\n"
            f"Скопируйте ключ и вставьте в VPN приложение.",
            parse_mode="Markdown",
            reply_markup=_build_device_keyboard(device_id)
        )
        return

    # === Refresh Key ===
    if data.startswith("refresh:"):
        device_id = int(data.split(":", 1)[1])

        async with SessionLocal() as db:
            try:
                from app.crud.spa import exchange_device_key
                device = await exchange_device_key(db, user, device_id)
                if not device:
                    await query.edit_message_text("❌ Устройство не найдено.")
                    return

                display_key = device.connection_key if len(device.connection_key) <= 400 else device.connection_key[:400] + "..."

                await query.edit_message_text(
                    f"✅ Ключ успешно обновлён!\n\n"
                    f"📱 *{device.name}*\n\n"
                    f"🔑 Новый VPN ключ:\n\n"
                    f"`{display_key}`\n\n"
                    f"Обновите настройки VPN приложения.",
                    parse_mode="Markdown",
                    reply_markup=_build_device_keyboard(device_id)
                )
            except RuntimeError as e:
                await query.edit_message_text(f"❌ Ошибка обновления ключа: {e}")
        return

    # === Delete Confirmation ===
    if data.startswith("delete_confirm:"):
        device_id = int(data.split(":", 1)[1])

        async with SessionLocal() as db:
            from app.crud.spa import list_devices
            devices = await list_devices(db, user)

        device = next((d for d in devices if d.id == device_id), None)
        if not device:
            await query.edit_message_text("❌ Устройство не найдено.")
            return

        await query.edit_message_text(
            f"🗑 *Удалить устройство?*\n\n"
            f"📱 {device.name}\n\n"
            f"• Это действие нельзя отменить\n"
            f"• Ключ VPN перестанет работать\n"
            f"• Баланс не будет возвращён",
            parse_mode="Markdown",
            reply_markup=_build_delete_keyboard(device_id)
        )
        return

    # === Delete Device ===
    if data.startswith("delete:"):
        device_id = int(data.split(":", 1)[1])

        async with SessionLocal() as db:
            try:
                from app.crud.spa import delete_device
                deleted = await delete_device(db, user, device_id)
                if not deleted:
                    await query.edit_message_text("❌ Устройство не найдено.")
                    return
            except RuntimeError as e:
                await query.edit_message_text(f"❌ Ошибка удаления: {e}")
                return

        await query.edit_message_text(
            "✅ Устройство успешно удалено.",
            reply_markup=_build_main_menu()
        )
        return


async def _add_device_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle device name input after selecting type."""
    if not update.effective_user or not update.message:
        return

    device_type = context.user_data.get("add_device_type")
    if not device_type:
        return  # Not waiting for device name

    device_name = update.message.text.strip()
    if len(device_name) < 2 or len(device_name) > 50:
        await update.message.reply_text("❌ Название должно быть от 2 до 50 символов. Попробуйте снова:")
        return

    user = await _get_user_by_telegram(update.effective_user.id)
    if not user:
        await update.message.reply_text("❌ Аккаунт не привязан.")
        context.user_data.pop("add_device_type", None)
        return

    if user.balance < 100:
        await update.message.reply_text(
            f"❌ Недостаточно средств. Стоимость устройства — 100 ₽.\n"
            f"Ваш баланс: {user.balance} ₽"
        )
        context.user_data.pop("add_device_type", None)
        await update.message.reply_text("Выберите действие:", reply_markup=_build_main_menu())
        return

    # Add device via API
    backend_url = settings.BACKEND_URL.rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{backend_url}/api/user/devices",
                json={"name": device_name, "type": device_type},
                headers={"Authorization": f"Bearer {context.user_data.get('auth_token', '')}"},
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка соединения: {e}")
        context.user_data.pop("add_device_type", None)
        return

    # Need to use internal endpoint or direct DB approach
    # For simplicity, let's use direct DB + XUI approach
    async with SessionLocal() as db:
        try:
            from app.crud.spa import create_device
            new_device = await create_device(db, user, device_name, device_type)

            type_labels = {"ios": "🍎 iOS", "android": "🤖 Android", "pc": "💻 PC"}
            await update.message.reply_text(
                f"✅ Устройство успешно добавлено!\n\n"
                f"📱 *{new_device.name}* ({type_labels.get(device_type, device_type)})\n"
                f"💰 Списано: 100 ₽\n\n"
                f"🔑 Ключ:\n"
                f"`{new_device.connection_key[:200]}...`\n\n"
                f"Скопируйте ключ и вставьте в VPN приложение.",
                parse_mode="Markdown",
                reply_markup=_build_main_menu()
            )
        except RuntimeError as e:
            await update.message.reply_text(f"❌ Ошибка добавления: {e}")

    context.user_data.pop("add_device_type", None)


async def _message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages — check if adding device or show menu."""
    if not update.effective_user or not update.message:
        return

    # Check if waiting for device name
    device_type = context.user_data.get("add_device_type")
    if device_type:
        await _add_device_message_handler(update, context)
        return

    # Check if user is linked
    user = await _get_user_by_telegram(update.effective_user.id)
    if user:
        await update.message.reply_text(
            "Выберите действие:",
            reply_markup=_build_main_menu()
        )


async def start_bot() -> None:
    global _application
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        return

    try:
        _application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        _application.add_handler(CommandHandler("start", _start_handler))
        _application.add_handler(CallbackQueryHandler(_device_callback_handler))
        _application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _message_handler))

        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling(drop_pending_updates=True)
        print("✓ Telegram bot started")
    except Exception as exc:
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
