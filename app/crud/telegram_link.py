from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link_token import LinkToken
from app.models.user import User

LINK_TOKEN_EXPIRE_MINUTES = 15


async def create_link_token(db: AsyncSession, user: User) -> str:
    """Create a new link token for user. Returns the token string."""
    # Delete old unused tokens
    await db.execute(
        delete(LinkToken).where(
            LinkToken.user_id == user.id,
            LinkToken.used.is_(False),
        )
    )

    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=LINK_TOKEN_EXPIRE_MINUTES)

    db.add(LinkToken(token=token, user_id=user.id, expires_at=expires_at))
    await db.commit()
    return token


async def check_link_status(db: AsyncSession, user: User) -> dict:
    """Check if user has linked Telegram."""
    return {
        "linked": user.telegram_id is not None,
        "telegram_username": f"@{user.telegram_username}" if user.telegram_username else None,
    }


async def confirm_link(
    db: AsyncSession,
    token: str,
    telegram_id: int,
    telegram_username: str | None = None,
    telegram_first_name: str | None = None,
) -> dict:
    """
    Confirm a link token and attach Telegram to user.
    Returns dict with success status and user email or error.
    """
    # Find token
    result = await db.execute(
        select(LinkToken).where(LinkToken.token == token)
    )
    link_token = result.scalar_one_or_none()

    if link_token is None:
        return {"error": "token_not_found"}

    if link_token.used:
        return {"error": "token_used"}

    expires_at = link_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return {"error": "token_expired"}

    # Get user
    user = await db.get(User, link_token.user_id)
    if user is None:
        return {"error": "token_not_found"}

    # Check if this telegram_id is already linked to another user
    existing = await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.id != user.id)
    )
    if existing.scalar_one_or_none() is not None:
        return {"error": "telegram_already_linked"}

    # Link Telegram to user
    user.telegram_id = telegram_id
    user.telegram_username = telegram_username
    user.telegram_linked_at = datetime.now(timezone.utc)

    link_token.used = True
    await db.commit()

    return {"success": True, "user_email": user.email}
