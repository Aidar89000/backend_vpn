import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.transaction import Transaction
from app.models.user import User
from app import xui_client

DEVICE_PRICE = 100


def _device_xui_email(user: User, device_id: int) -> str:
    local, _, domain = user.email.partition("@")
    safe_local = "".join(ch if ch.isalnum() else "_" for ch in local) or "user"
    safe_domain = domain or "local"
    return f"{safe_local}.device{device_id}@{safe_domain}"


def _client_id_from_link(link: str) -> str | None:
    try:
        parsed = urlparse(link)
        if parsed.scheme != "vless":
            return None
        if not parsed.username:
            return None
        return parsed.username
    except Exception:
        return None


def _format_expiry(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def _format_tx_date(dt: datetime) -> str:
    return dt.strftime("%H:%M")


async def _create_remote_key(xui_email: str) -> tuple[str, str]:
    """Create a new XUI client (for brand-new devices)."""
    inbounds_result = await asyncio.to_thread(xui_client.get_inbounds_result)
    if not inbounds_result["success"]:
        raise RuntimeError(inbounds_result["error"] or "3X-UI inbounds are unavailable")

    inbound = inbounds_result["inbounds"][0]
    result = await asyncio.to_thread(
        xui_client.add_client,
        inbound_id=inbound.id,
        email=xui_email,
        flow="",
    )
    if result.get("error"):
        raise RuntimeError(result["error"])
    if not result.get("link"):
        raise RuntimeError("3X-UI did not return a connection link")
    return result["link"], result["uuid"]


async def _recreate_remote_key(xui_email: str) -> tuple[str, str]:
    """Delete old XUI client and create a new one (for key exchange)."""
    inbounds_result = await asyncio.to_thread(xui_client.get_inbounds_result)
    if not inbounds_result["success"]:
        raise RuntimeError(inbounds_result["error"] or "3X-UI inbounds are unavailable")

    inbound = inbounds_result["inbounds"][0]
    deleted = await asyncio.to_thread(xui_client.delete_client_by_email, xui_email)
    if not deleted:
        raise RuntimeError(f"Failed to remove previous 3X-UI client for {xui_email}")
    result = await asyncio.to_thread(
        xui_client.add_client,
        inbound_id=inbound.id,
        email=xui_email,
        flow="",
    )
    if result.get("error"):
        raise RuntimeError(result["error"])
    if not result.get("link"):
        raise RuntimeError("3X-UI did not return a connection link")
    return result["link"], result["uuid"]


async def list_devices(db: AsyncSession, user: User) -> list[Device]:
    result = await db.execute(
        select(Device)
        .where(Device.user_id == user.id)
        .order_by(Device.created_at.desc())
    )
    return list(result.scalars().all())


async def list_transactions(db: AsyncSession, user: User) -> list[Transaction]:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
    )
    return list(result.scalars().all())


async def add_transaction(
    db: AsyncSession,
    user: User,
    tx_type: str,
    amount: int,
    description: str,
) -> Transaction:
    transaction = Transaction(
        user_id=user.id,
        type=tx_type,
        amount=amount,
        description=description,
    )
    db.add(transaction)
    await db.flush()
    return transaction


async def create_device(db: AsyncSession, user: User, name: str, device_type: str) -> Device:
    user.balance -= DEVICE_PRICE
    expiry_at = datetime.now(timezone.utc) + timedelta(days=30)
    device = Device(
        user_id=user.id,
        name=name,
        device_type=device_type,
        status="active",
        expiry_at=expiry_at,
        connection_key="pending",
    )
    db.add(device)
    await db.flush()
    device.xui_email = _device_xui_email(user, device.id)
    link, client_id = await _create_remote_key(device.xui_email)
    device.connection_key = link
    device.xui_client_id = client_id
    await add_transaction(db, user, "purchase", -DEVICE_PRICE, "Новое устройство")
    await db.commit()
    await db.refresh(device)
    await db.refresh(user)
    return device


async def update_device_name(db: AsyncSession, user: User, device_id: int, name: str) -> Device | None:
    device = await db.get(Device, device_id)
    if not device or device.user_id != user.id:
        return None
    device.name = name
    await db.commit()
    await db.refresh(device)
    return device


async def exchange_device_key(db: AsyncSession, user: User, device_id: int) -> Device | None:
    device = await db.get(Device, device_id)
    if not device or device.user_id != user.id:
        return None
    xui_email = device.xui_email or _device_xui_email(user, device.id)
    link, client_id = await _recreate_remote_key(xui_email)
    device.xui_email = xui_email
    device.xui_client_id = client_id
    device.connection_key = link
    await add_transaction(db, user, "purchase", 0, "Обновление ключа")
    await db.commit()
    await db.refresh(device)
    return device


async def delete_device(db: AsyncSession, user: User, device_id: int) -> bool:
    device = await db.get(Device, device_id)
    if not device or device.user_id != user.id:
        return False
    if device.xui_email:
        deleted = await asyncio.to_thread(xui_client.delete_client_by_email, device.xui_email)
        if not deleted:
            raise RuntimeError("Failed to delete client in 3X-UI")
    elif device.xui_client_id:
        inbounds_result = await asyncio.to_thread(xui_client.get_inbounds_result)
        if not inbounds_result["success"]:
            raise RuntimeError(inbounds_result["error"] or "3X-UI inbounds are unavailable")
        inbound = inbounds_result["inbounds"][0]
        deleted = await asyncio.to_thread(xui_client.delete_client, inbound.id, device.xui_client_id)
        if not deleted:
            raise RuntimeError("Failed to delete client in 3X-UI")
    await db.delete(device)
    await db.commit()
    return True


async def top_up_balance(db: AsyncSession, user: User, amount: int) -> int:
    user.balance += amount
    await add_transaction(db, user, "topup", amount, "Пополнение счета")
    await db.commit()
    await db.refresh(user)
    return user.balance


def serialize_device(device: Device) -> dict:
    return {
        "id": str(device.id),
        "name": device.name,
        "type": device.device_type,
        "status": device.status,
        "expiryDate": _format_expiry(device.expiry_at),
        "key": device.connection_key,
    }


def serialize_transaction(transaction: Transaction) -> dict:
    return {
        "id": str(transaction.id),
        "type": transaction.type,
        "amount": transaction.amount,
        "date": _format_tx_date(transaction.created_at),
        "description": transaction.description,
    }
