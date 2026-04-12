from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from urllib.parse import parse_qs, unquote

from fastapi import APIRouter, Depends, HTTPException, Header, status
from jose import jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import xui_client
from app.config import get_settings
from app.crud.spa import (
    DEVICE_PRICE,
    create_device,
    delete_device,
    exchange_device_key,
    list_devices,
    list_transactions,
    serialize_device,
    serialize_transaction,
    top_up_balance,
    update_device_name,
)
from app.crud.telegram_link import create_link_token, check_link_status, confirm_link
from app.crud.user import create_user, get_user_by_email, get_user_by_username, verify_password
from app.database import get_db
from app.dependencies import get_current_user
from app.models.email_verification_code import EmailVerificationCode
from app.models.telegram_auth_code import TelegramAuthCode
from app.models.user import User
from app.schemas.spa import (
    DeviceCreateRequest,
    DeviceResponse,
    EmailCodeRequest,
    DeviceUpdateRequest,
    EmailLoginRequest,
    EmailPasswordRequest,
    MessageResponse,
    ProfileResponse,
    SessionResponse,
    SessionUser,
    TelegramLoginRequest,
    TopUpRequest,
    TopUpResponse,
    TransactionResponse,
    LinkTokenResponse,
    LinkStatusResponse,
    ConfirmLinkRequest,
    ConfirmLinkResponse,
)
from app.services.mail import EmailDeliveryError, send_login_code_email


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp initData and return parsed user data."""
    # parse_qs already does URL decoding — don't pre-unquote
    parsed = parse_qs(init_data)
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        print(f"[validate_init] No hash found in parsed data")
        return None

    # Remove hash from data for verification
    data_check_parts = {k: v[0] for k, v in parsed.items() if k != "hash"}
    sorted_parts = sorted(data_check_parts.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_parts)

    # Compute HMAC
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    print(f"[validate_init] Received hash: {received_hash}")
    print(f"[validate_init] Computed hash: {computed_hash}")
    print(f"[validate_init] Data check string (first 300): {data_check_string[:300]}")

    if not hmac.compare_digest(computed_hash, received_hash):
        print(f"[validate_init] Hash mismatch!")
        return None

    # Parse user data
    user_data = data_check_parts.get("user")
    if not user_data:
        print(f"[validate_init] No user data found")
        return None

    try:
        user = json.loads(user_data)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[validate_init] Failed to parse user JSON: {e}")
        return None

    print(f"[validate_init] Success! user_id={user.get('id')}")
    return user

from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/api", tags=["spa"])
settings = get_settings()


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _username_from_email(email: str) -> str:
    local = email.split("@", 1)[0].replace(".", "_").replace("-", "_")
    clean = "".join(ch for ch in local if ch.isalnum() or ch == "_").strip("_") or "user"
    return clean[:40]


async def _get_or_create_email_user(db: AsyncSession, email: str):
    user = await get_user_by_email(db, email)
    if user:
        return user

    base_username = _username_from_email(email)
    username = base_username
    suffix = 1
    while await get_user_by_username(db, username):
        suffix += 1
        username = f"{base_username}_{suffix}"

    return await create_user(
        db,
        UserCreate(
            username=username,
            email=email,
            password=secrets.token_urlsafe(16),
        ),
    )


def _generate_code() -> str:
    return f"{secrets.randbelow(10000):04d}"


@router.post("/auth/request-code", response_model=MessageResponse)
async def request_email_code(payload: EmailCodeRequest, db: AsyncSession = Depends(get_db)):
    if not settings.EMAIL_DELIVERY_ENABLED and not (settings.DEBUG and settings.EMAIL_DEV_LOG_ONLY):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured on the server",
        )

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_CODE_EXPIRE_MINUTES)

    await db.execute(delete(EmailVerificationCode).where(EmailVerificationCode.email == payload.email))
    db.add(
        EmailVerificationCode(
            email=payload.email,
            code=code,
            expires_at=expires_at,
        )
    )
    await db.commit()

    try:
        await send_login_code_email(payload.email, code)
    except EmailDeliveryError as exc:
        await db.execute(delete(EmailVerificationCode).where(EmailVerificationCode.email == payload.email))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send verification email: {exc}",
        ) from exc

    return MessageResponse(message="Verification code sent")


@router.post("/auth/email-login", response_model=SessionResponse)
async def email_login(payload: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    code = payload.code.strip()
    if len(code) != 4 or not code.isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    result = await db.execute(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == payload.email,
            EmailVerificationCode.code == code,
            EmailVerificationCode.is_used.is_(False),
        )
        .order_by(EmailVerificationCode.created_at.desc())
    )
    verification = result.scalar_one_or_none()
    if verification is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    expires_at = verification.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired")

    verification.is_used = True
    user = await _get_or_create_email_user(db, payload.email)
    await db.commit()
    await db.refresh(user)
    return SessionResponse(
        access_token=create_access_token(user.id),
        user=SessionUser(id=user.id, email=user.email, balance=user.balance),
    )


@router.post("/auth/login", response_model=SessionResponse)
async def email_password_login(payload: EmailPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, payload.email)
    if not user:
        # Пользователь не существует - ошибка, а не автоматическая регистрация
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден. Пожалуйста, зарегистрируйтесь."
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль")

    return SessionResponse(
        access_token=create_access_token(user.id),
        user=SessionUser(id=user.id, email=user.email, balance=user.balance),
    )


@router.post("/auth/register", response_model=SessionResponse)
async def email_register(payload: EmailPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Проверяем, существует ли пользователь
    existing_user = await get_user_by_email(db, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже существует"
        )
    
    # Создаём нового пользователя
    base_username = _username_from_email(payload.email)
    username = base_username
    suffix = 1
    while await get_user_by_username(db, username):
        suffix += 1
        username = f"{base_username}_{suffix}"
    
    user = await create_user(
        db,
        UserCreate(username=username, email=payload.email, password=payload.password),
    )
    
    await db.commit()
    await db.refresh(user)
    
    return SessionResponse(
        access_token=create_access_token(user.id),
        user=SessionUser(id=user.id, email=user.email, balance=user.balance),
    )


@router.post("/auth/telegram-login", response_model=SessionResponse)
async def telegram_login(payload: TelegramLoginRequest, db: AsyncSession = Depends(get_db)):
    code = payload.code.strip()
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный код")

    result = await db.execute(
        select(TelegramAuthCode)
        .where(
            TelegramAuthCode.code == code,
            TelegramAuthCode.is_used.is_(False),
        )
        .order_by(TelegramAuthCode.created_at.desc())
    )
    auth_code = result.scalar_one_or_none()
    if auth_code is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный код")

    expires_at = auth_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Код истёк")

    auth_code.is_used = True

    telegram_id = auth_code.telegram_id
    tg_email = f"tg_{telegram_id}@telegram.local"

    user = await get_user_by_email(db, tg_email)
    if not user:
        tg_username = auth_code.telegram_username or str(telegram_id)
        base_username = f"tg_{tg_username}"
        username = base_username
        suffix = 1
        while await get_user_by_username(db, username):
            suffix += 1
            username = f"{base_username}_{suffix}"
        user = await create_user(
            db,
            UserCreate(username=username, email=tg_email, password=secrets.token_urlsafe(32)),
        )

    await db.commit()
    await db.refresh(user)
    return SessionResponse(
        access_token=create_access_token(user.id),
        user=SessionUser(id=user.id, email=user.email, balance=user.balance),
    )


@router.post("/auth/telegram-webapp", response_model=SessionResponse)
async def telegram_webapp_login(payload: dict, db: AsyncSession = Depends(get_db)):
    """Auto-login via Telegram WebApp initData."""
    init_data = payload.get("init_data", "").strip()
    if not init_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="init_data required")

    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram not configured")

    # Debug logging
    print(f"[telegram-webapp] Received init_data (first 100 chars): {init_data[:100]}")

    user_data = validate_telegram_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)
    if not user_data:
        print(f"[telegram-webapp] HMAC validation failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user id in initData")

    # Find user by telegram_id
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram account not linked to any user")

    # Update telegram username if available
    tg_username = user_data.get("username")
    if tg_username and user.telegram_username != tg_username:
        user.telegram_username = tg_username
        await db.commit()

    return SessionResponse(
        access_token=create_access_token(user.id),
        user=SessionUser(id=user.id, email=user.email, balance=user.balance),
    )


@router.get("/user/profile", response_model=ProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return ProfileResponse(
        email=current_user.email,
        balance=current_user.balance,
        telegram_id=current_user.telegram_id,
        telegram_username=current_user.telegram_username,
    )


@router.get("/user/dashboard-data")
async def get_dashboard_data(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """Get all dashboard data in parallel for faster response."""
    from app.crud.spa import get_user_data_parallel, serialize_device, serialize_transaction
    
    data = await get_user_data_parallel(db, current_user)
    
    return {
        "profile": data["profile"],
        "devices": [serialize_device(device) for device in data["devices"]],
        "transactions": [serialize_transaction(tx) for tx in data["transactions"]],
    }


@router.get("/debug/xui")
async def debug_xui(current_user: UserResponse = Depends(get_current_user)):
    result = xui_client.get_inbounds_result()
    
    # Детальная отладка inbound
    debug_info = {
        "success": result["success"],
        "error": result["error"],
        "inbounds_count": len(result["inbounds"]),
    }
    
    if result["inbounds"]:
        inbound = result["inbounds"][0]
        debug_info["first_inbound"] = {
            "id": getattr(inbound, 'id', None),
            "protocol": getattr(inbound, 'protocol', None),
            "port": getattr(inbound, 'port', None),
        }
        
        # Проверяем stream_settings
        stream = getattr(inbound, 'stream_settings', None)
        if hasattr(stream, 'model_dump'):
            stream_dict = stream.model_dump(by_alias=True)
            debug_info["stream_settings"] = stream_dict
            debug_info["stream_type"] = "StreamSettings object"
        elif isinstance(stream, dict):
            stream_dict = stream
            debug_info["stream_settings"] = stream_dict
            debug_info["stream_type"] = "dict"
        elif isinstance(stream, str):
            debug_info["stream_settings"] = stream[:500]
            debug_info["stream_type"] = "string"
        else:
            debug_info["stream_settings"] = None
            debug_info["stream_type"] = type(stream).__name__
    
    return debug_info


@router.get("/user/devices", response_model=list[DeviceResponse])
async def get_devices(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    devices = await list_devices(db, current_user)
    return [DeviceResponse(**serialize_device(device)) for device in devices]


@router.post("/user/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def add_device(
    payload: DeviceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    if current_user.balance < DEVICE_PRICE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")

    try:
        device = await create_device(db, current_user, payload.name.strip(), payload.type.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"3X-UI error: {exc}") from exc
    return DeviceResponse(**serialize_device(device))


@router.patch("/user/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_device(
    device_id: int,
    payload: DeviceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    device = await update_device_name(db, current_user, device_id, payload.name.strip())
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")


@router.post("/user/devices/{device_id}/exchange")
async def exchange_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    try:
        device = await exchange_device_key(db, current_user, device_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"3X-UI error: {exc}") from exc
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return {"key": device.connection_key}


@router.delete("/user/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    try:
        deleted = await delete_device(db, current_user, device_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"3X-UI error: {exc}") from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")


@router.get("/user/transactions", response_model=list[TransactionResponse])
async def get_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    transactions = await list_transactions(db, current_user)
    return [TransactionResponse(**serialize_transaction(tx)) for tx in transactions]


@router.post("/user/topup", response_model=TopUpResponse)
async def topup(
    payload: TopUpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    if payload.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")
    new_balance = await top_up_balance(db, current_user, payload.amount)
    return TopUpResponse(newBalance=new_balance)


# === Telegram Link Endpoints ===

@router.post("/telegram/link-token", response_model=LinkTokenResponse)
async def generate_link_token(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a deep link token for Telegram account linking."""
    # Check if already linked
    if current_user.telegram_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telegram already linked to this account"
        )

    token = await create_link_token(db, current_user)
    bot_username = settings.TELEGRAM_BOT_USERNAME if hasattr(settings, 'TELEGRAM_BOT_USERNAME') else "your_bot_name"

    return LinkTokenResponse(
        token=token,
        bot_username=bot_username,
        deep_link=f"https://t.me/{bot_username}?start={token}",
        expires_in=900,
    )


@router.get("/telegram/link-status", response_model=LinkStatusResponse)
async def get_link_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if Telegram has been linked."""
    status = await check_link_status(db, current_user)
    return LinkStatusResponse(**status)


@router.post("/internal/telegram/confirm-link", response_model=ConfirmLinkResponse)
async def internal_confirm_link(
    payload: ConfirmLinkRequest,
    db: AsyncSession = Depends(get_db),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    """Internal endpoint for Telegram bot to confirm link."""
    # Verify internal secret
    if x_internal_secret != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await confirm_link(
        db,
        payload.token,
        payload.telegram_id,
        payload.telegram_username,
        payload.telegram_first_name,
    )

    if "error" in result:
        error = result["error"]
        if error == "token_expired":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token_expired")
        elif error == "token_used":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token_used")
        elif error == "token_not_found":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token_not_found")
        elif error == "telegram_already_linked":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="telegram_already_linked")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return ConfirmLinkResponse(success=True, user_email=result["user_email"])
