"""
CRUD operations for VPN keys
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.vpn_key import VPNKey
from app.schemas.vpn_key import VPNKeyCreate, VPNKeyUpdate


async def get_vpn_key(db: AsyncSession, key_id: int) -> VPNKey | None:
    """Get VPN key by ID."""
    return await db.get(VPNKey, key_id)


async def get_vpn_key_by_email(db: AsyncSession, email: str) -> VPNKey | None:
    """Get VPN key by email."""
    result = await db.execute(select(VPNKey).where(VPNKey.email == email))
    return result.scalar_one_or_none()


async def get_vpn_keys(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    user_id: int = None,
    is_active: bool = None,
) -> list[VPNKey]:
    """Get list of VPN keys with optional filters."""
    query = select(VPNKey)
    
    if user_id is not None:
        query = query.where(VPNKey.user_id == user_id)
    
    if is_active is not None:
        query = query.where(VPNKey.is_active == is_active)
    
    result = await db.execute(query.order_by(VPNKey.created_at.desc()).offset(skip).limit(limit))
    return list(result.scalars().all())


async def create_vpn_key(db: AsyncSession, vpn_key_data: VPNKeyCreate) -> VPNKey:
    """Create a new VPN key."""
    db_vpn_key = VPNKey(
        user_id=vpn_key_data.user_id,
        email=vpn_key_data.email,
        uuid=vpn_key_data.uuid,
        inbound_id=vpn_key_data.inbound_id,
        protocol=vpn_key_data.protocol,
        connection_link=vpn_key_data.connection_link,
        subscription_url=vpn_key_data.subscription_url,
        limit_ip=vpn_key_data.limit_ip,
        total_gb=vpn_key_data.total_gb,
        expire_time=vpn_key_data.expire_time,
        is_active=True,
    )
    db.add(db_vpn_key)
    await db.commit()
    await db.refresh(db_vpn_key)
    return db_vpn_key


async def update_vpn_key(db: AsyncSession, db_vpn_key: VPNKey, update_data: VPNKeyUpdate) -> VPNKey:
    """Update VPN key."""
    update_data_dict = update_data.model_dump(exclude_unset=True)
    
    for field, value in update_data_dict.items():
        setattr(db_vpn_key, field, value)
    
    await db.commit()
    await db.refresh(db_vpn_key)
    return db_vpn_key


async def delete_vpn_key(db: AsyncSession, key_id: int) -> bool:
    """Delete VPN key."""
    db_vpn_key = await db.get(VPNKey, key_id)
    if db_vpn_key:
        await db.delete(db_vpn_key)
        await db.commit()
        return True
    return False


async def deactivate_vpn_key(db: AsyncSession, key_id: int) -> VPNKey | None:
    """Deactivate VPN key (soft delete)."""
    db_vpn_key = await db.get(VPNKey, key_id)
    if db_vpn_key:
        db_vpn_key.is_active = False
        await db.commit()
        await db.refresh(db_vpn_key)
    return db_vpn_key


async def get_user_vpn_keys(db: AsyncSession, user_id: int) -> list[VPNKey]:
    """Get all VPN keys for a specific user."""
    result = await db.execute(
        select(VPNKey)
        .where(VPNKey.user_id == user_id, VPNKey.is_active.is_(True))
        .order_by(VPNKey.created_at.desc())
    )
    return list(result.scalars().all())


async def count_vpn_keys(db: AsyncSession, user_id: int = None) -> int:
    """Count VPN keys."""
    query = select(func.count(VPNKey.id))
    if user_id is not None:
        query = query.where(VPNKey.user_id == user_id)
    result = await db.execute(query)
    return int(result.scalar_one())
