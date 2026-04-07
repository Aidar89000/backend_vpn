"""
VPN Key Management Router
"""
from typing import Annotated, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.user import UserResponse, Message
from app.schemas.vpn_key import (
    VPNKeyGenerate,
    VPNKeyResponse,
    VPNKeyWithLink,
    InboundResponse,
    ServerStats,
    ClientTraffic,
)
from app.crud.vpn_key import (
    create_vpn_key,
    get_vpn_key,
    get_vpn_keys,
    get_user_vpn_keys,
    deactivate_vpn_key,
)
from app import xui_client

router = APIRouter(prefix="/vpn", tags=["vpn"])


# ==================== API Endpoints ====================

@router.get("/inbounds", response_model=list[InboundResponse])
async def get_inbounds(
    current_user: Annotated[UserResponse, Depends(get_current_user)]
):
    """Get all available inbounds from XUI panel."""
    inbounds = xui_client.get_inbounds()
    
    result = []
    for inbound in inbounds:
        clients = inbound.settings.get('clients', []) if hasattr(inbound, 'settings') and inbound.settings else []
        result.append(InboundResponse(
            id=inbound.id,
            protocol=inbound.protocol,
            port=inbound.port,
            listen=getattr(inbound, 'listen', None),
            client_count=len(clients),
        ))
    
    return result


@router.get("/stats", response_model=ServerStats)
async def get_server_stats(
    current_user: Annotated[UserResponse, Depends(get_current_user)]
):
    """Get server statistics."""
    stats = xui_client.get_server_stats()
    return ServerStats(**stats)


@router.post("/generate", response_model=VPNKeyWithLink, status_code=status.HTTP_201_CREATED)
async def generate_vpn_key(
    key_data: VPNKeyGenerate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[UserResponse, Depends(get_current_user)]
):
    """Generate a new VPN key."""
    # Check if email already exists
    from app.crud.vpn_key import get_vpn_key_by_email
    existing = await get_vpn_key_by_email(db, key_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    # Calculate expire time
    expire_time = 0
    if key_data.expire_days > 0:
        expire_time = int((datetime.now(timezone.utc) + timedelta(days=key_data.expire_days)).timestamp() * 1000)
    
    # Add client to XUI
    result = xui_client.add_client(
        inbound_id=key_data.inbound_id,
        email=key_data.email,
        limit_ip=key_data.limit_ip,
        total_gb=key_data.total_gb,
        expire_time=expire_time,
        flow=key_data.flow,
    )
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    # Save to database
    from app.schemas.vpn_key import VPNKeyCreate
    vpn_key_create = VPNKeyCreate(
        user_id=current_user.id,
        email=key_data.email,
        uuid=result["uuid"],
        inbound_id=key_data.inbound_id,
        protocol=key_data.protocol,
        connection_link=result.get("link"),
        subscription_url=result.get("subscription_url"),
        limit_ip=key_data.limit_ip,
        total_gb=key_data.total_gb,
        expire_time=expire_time,
    )
    
    db_vpn_key = await create_vpn_key(db, vpn_key_create)
    return db_vpn_key


@router.get("/keys", response_model=list[VPNKeyResponse])
async def get_my_vpn_keys(
    skip: int = 0,
    limit: int = 100,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Get all VPN keys for current user."""
    return await get_user_vpn_keys(db, current_user.id)


@router.get("/keys/all", response_model=list[VPNKeyResponse])
async def get_all_vpn_keys(
    skip: int = 0,
    limit: int = 100,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Get all VPN keys (admin)."""
    return await get_vpn_keys(db, skip=skip, limit=limit)


@router.get("/keys/{key_id}", response_model=VPNKeyResponse)
async def get_vpn_key_info(
    key_id: int,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Get VPN key information."""
    db_vpn_key = await get_vpn_key(db, key_id)
    if not db_vpn_key:
        raise HTTPException(status_code=404, detail="VPN key not found")
    
    # Check ownership
    if db_vpn_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return db_vpn_key


@router.delete("/keys/{key_id}", response_model=Message)
async def revoke_vpn_key(
    key_id: int,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Revoke (deactivate) a VPN key."""
    db_vpn_key = await get_vpn_key(db, key_id)
    if not db_vpn_key:
        raise HTTPException(status_code=404, detail="VPN key not found")
    
    # Check ownership
    if db_vpn_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Delete from XUI
    xui_client.delete_client(db_vpn_key.inbound_id, db_vpn_key.uuid)
    
    # Deactivate in database
    await deactivate_vpn_key(db, key_id)
    
    return {"message": "VPN key successfully revoked"}


@router.get("/keys/{key_id}/traffic", response_model=ClientTraffic)
async def get_vpn_key_traffic(
    key_id: int,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Get traffic statistics for a VPN key."""
    db_vpn_key = await get_vpn_key(db, key_id)
    if not db_vpn_key:
        raise HTTPException(status_code=404, detail="VPN key not found")
    
    # Check ownership
    if db_vpn_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    traffic = xui_client.get_client_traffic(db_vpn_key.inbound_id, db_vpn_key.uuid)
    
    if "error" in traffic:
        raise HTTPException(status_code=404, detail=traffic["error"])
    
    return ClientTraffic(**traffic)


@router.post("/keys/{key_id}/reset-traffic", response_model=Message)
async def reset_vpn_key_traffic(
    key_id: int,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Reset traffic statistics for a VPN key."""
    db_vpn_key = await get_vpn_key(db, key_id)
    if not db_vpn_key:
        raise HTTPException(status_code=404, detail="VPN key not found")
    
    # Check ownership
    if db_vpn_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    success = xui_client.reset_client_traffic(db_vpn_key.inbound_id, db_vpn_key.uuid)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to reset traffic")
    
    return {"message": "Traffic successfully reset"}


# ==================== Web Endpoints ====================

@router.get("/panel", response_class=HTMLResponse)
async def vpn_panel_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """VPN management panel page."""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    
    # Get user's VPN keys
    vpn_keys = await get_user_vpn_keys(db, current_user.id)
    
    # Get inbounds
    inbounds = xui_client.get_inbounds()
    
    return templates.TemplateResponse(
        "vpn_panel.html",
        {
            "request": request,
            "user": current_user,
            "vpn_keys": vpn_keys,
            "inbounds": inbounds,
        }
    )


@router.get("/new", response_class=HTMLResponse)
async def vpn_new_key_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[UserResponse, Depends(get_current_user)] = None
):
    """Generate new VPN key page."""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    
    # Get inbounds
    inbounds = xui_client.get_inbounds()
    
    return templates.TemplateResponse(
        "vpn_new.html",
        {
            "request": request,
            "user": current_user,
            "inbounds": inbounds,
        }
    )
