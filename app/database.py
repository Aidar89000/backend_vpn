from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(
    engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async with SessionLocal() as db:
        yield db


async def init_db():
    """Initialize database tables."""
    import app.models  # noqa: F401

    def ensure_sqlite_columns(sync_conn):
        inspector = sync_conn.exec_driver_sql("PRAGMA table_info(devices)")
        existing_columns = {row[1] for row in inspector.fetchall()}
        if "xui_email" not in existing_columns:
            sync_conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN xui_email VARCHAR(255)")
        if "xui_client_id" not in existing_columns:
            sync_conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN xui_client_id VARCHAR(255)")

        # User telegram columns
        user_inspector = sync_conn.exec_driver_sql("PRAGMA table_info(users)")
        user_columns = {row[1] for row in user_inspector.fetchall()}
        if "telegram_id" not in user_columns:
            sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN telegram_id BIGINT")
        if "telegram_username" not in user_columns:
            sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN telegram_username VARCHAR(255)")
        if "telegram_linked_at" not in user_columns:
            sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN telegram_linked_at TIMESTAMP")

        # Transaction platega columns
        transaction_inspector = sync_conn.exec_driver_sql("PRAGMA table_info(transactions)")
        transaction_columns = {row[1] for row in transaction_inspector.fetchall()}
        if "platega_transaction_id" not in transaction_columns:
            sync_conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN platega_transaction_id VARCHAR(36)")
        if "platega_status" not in transaction_columns:
            sync_conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN platega_status VARCHAR(32)")
        if "platega_url" not in transaction_columns:
            sync_conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN platega_url TEXT")
        if "platega_expires_in" not in transaction_columns:
            sync_conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN platega_expires_in VARCHAR(16)")
        if "platega_rate" not in transaction_columns:
            sync_conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN platega_rate FLOAT")
        if "platega_payload" not in transaction_columns:
            sync_conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN platega_payload TEXT")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_sqlite_columns)
