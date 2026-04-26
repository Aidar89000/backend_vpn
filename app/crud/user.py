import base64
import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


def get_password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)
    return "pbkdf2_sha256$390000$%s$%s" % (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations, salt_b64, hash_b64 = hashed_password.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _is_legacy_user_schema_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no such column" in message and "users.telegram_" in message


def _build_legacy_user(row) -> User | None:
    if row is None:
        return None

    user = User(
        username=row.username,
        email=row.email,
        hashed_password=row.hashed_password,
        balance=row.balance,
        is_active=bool(row.is_active),
    )
    user.id = row.id
    user.created_at = row.created_at
    user.updated_at = row.updated_at
    user.telegram_id = None
    user.telegram_username = None
    user.telegram_linked_at = None
    return user


async def _get_legacy_user_by_field(db: AsyncSession, field: str, value) -> User | None:
    query = (
        f"SELECT id, username, email, hashed_password, balance, is_active, created_at, updated_at "
        f"FROM users WHERE {field} = :value LIMIT 1"
    )
    result = await db.exec_driver_sql(query, {"value": value})
    return _build_legacy_user(result.first())


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    try:
        return await db.get(User, user_id)
    except OperationalError as exc:
        if not _is_legacy_user_schema_error(exc):
            raise
        return await _get_legacy_user_by_field(db, "id", user_id)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    try:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    except OperationalError as exc:
        if not _is_legacy_user_schema_error(exc):
            raise
        return await _get_legacy_user_by_field(db, "username", username)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    try:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    except OperationalError as exc:
        if not _is_legacy_user_schema_error(exc):
            raise
        return await _get_legacy_user_by_field(db, "email", email)


async def create_user(db: AsyncSession, user: UserCreate) -> User:
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
    )
    db.add(db_user)
    try:
        await db.commit()
        await db.refresh(db_user)
        return db_user
    except OperationalError as exc:
        await db.rollback()
        if not _is_legacy_user_schema_error(exc):
            raise

    hashed_password = get_password_hash(user.password)
    await db.exec_driver_sql(
        """
        INSERT INTO users (username, email, hashed_password, balance, is_active)
        VALUES (:username, :email, :hashed_password, :balance, :is_active)
        """,
        {
            "username": user.username,
            "email": user.email,
            "hashed_password": hashed_password,
            "balance": 1000,
            "is_active": True,
        },
    )
    await db.commit()
    legacy_user = await _get_legacy_user_by_field(db, "email", user.email)
    if legacy_user is None:
        raise RuntimeError("User insert succeeded but user could not be reloaded")
    return legacy_user


async def update_user(db: AsyncSession, db_user: User, user_update: UserUpdate) -> User:
    update_data = user_update.model_dump(exclude_unset=True)
    
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    db_user = await db.get(User, user_id)
    if db_user:
        await db.delete(db_user)
        await db.commit()
        return True
    return False


async def update_user_balance(db: AsyncSession, user_id: int, amount: int) -> User | None:
    user = await get_user(db, user_id)
    if user:
        user.balance += amount
        await db.commit()
        await db.refresh(user)
        return user
    return None


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
