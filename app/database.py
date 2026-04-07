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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_sqlite_columns)
