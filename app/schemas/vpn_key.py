"""
Pydantic schemas for VPN keys
"""
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class VPNKeyBase(BaseModel):
    email: str
    inbound_id: int
    protocol: str
    limit_ip: int = 0
    total_gb: int = 0
    expire_time: int = 0


class VPNKeyCreate(VPNKeyBase):
    uuid: str
    connection_link: Optional[str] = None
    subscription_url: Optional[str] = None
    user_id: Optional[int] = None


class VPNKeyUpdate(BaseModel):
    email: Optional[str] = None
    limit_ip: Optional[int] = None
    total_gb: Optional[int] = None
    expire_time: Optional[int] = None
    is_active: Optional[bool] = None
    connection_link: Optional[str] = None
    subscription_url: Optional[str] = None


class VPNKeyResponse(VPNKeyBase):
    id: int
    user_id: Optional[int] = None
    uuid: str
    connection_link: Optional[str] = None
    subscription_url: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class VPNKeyGenerate(BaseModel):
    """Schema for generating a new VPN key."""
    email: str
    inbound_id: int
    protocol: str = "vless"
    limit_ip: int = 0
    total_gb: int = 0
    expire_days: int = 0  # 0 = unlimited
    flow: str = ""
    user_id: Optional[int] = None

    @field_validator("email")
    @classmethod
    def email_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Email cannot be empty")
        return v.strip()

    @field_validator("expire_days")
    @classmethod
    def expire_days_positive(cls, v):
        if v < 0:
            raise ValueError("Expire days must be non-negative")
        return v


class VPNKeyWithLink(VPNKeyResponse):
    """VPN key response with connection link."""
    connection_link: str


class InboundResponse(BaseModel):
    """Inbound response schema."""
    id: int
    protocol: str
    port: int
    listen: Optional[str] = None
    client_count: int = 0

    class Config:
        from_attributes = True


class ServerStats(BaseModel):
    """Server statistics."""
    inbounds: int
    total_clients: int
    active_clients: int
    total_upload: int = 0
    total_download: int = 0
    total_traffic: int = 0


class ClientTraffic(BaseModel):
    """Client traffic information."""
    email: str
    upload: int = 0
    download: int = 0
    total: int = 0
    total_gb: int = 0
    expiry_time: int = 0
    enable: bool = True
