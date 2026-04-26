from sqlalchemy import DateTime, ForeignKey, Integer, String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Platega fields
    platega_transaction_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True, unique=True)
    platega_status: Mapped[str] = mapped_column(String(32), nullable=True)
    platega_url: Mapped[str] = mapped_column(Text, nullable=True)
    platega_expires_in: Mapped[str] = mapped_column(String(16), nullable=True)
    platega_rate: Mapped[float] = mapped_column(Float, nullable=True)
    platega_payload: Mapped[str] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="transactions")
