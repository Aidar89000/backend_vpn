from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class VPNKey(Base):
    """VPN key model for storing generated VPN credentials."""
    __tablename__ = "vpn_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    uuid: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    inbound_id: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_link: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    subscription_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    limit_ip: Mapped[int] = mapped_column(Integer, default=0)
    total_gb: Mapped[int] = mapped_column(BigInteger, default=0)
    expire_time: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="vpn_keys")

    def __repr__(self):
        return f"<VPNKey {self.email}>"
