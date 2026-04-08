from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine, init_db
from app.routers import auth, spa, vpn
from app.services.telegram_bot import start_bot, stop_bot

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print(f"Starting {settings.APP_NAME}...")
    await init_db()
    print("✓ Database initialized")

    try:
        await start_bot()
    except Exception as exc:
        print(f"⚠ Telegram bot startup failed (continuing anyway): {exc}")
        print("Application will start without Telegram authentication")

    print("✓ Application started successfully")
    yield
    print("Shutting down application...")
    try:
        await stop_bot()
    except Exception:
        pass
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="VPN Key Manager API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - разрешаем запросы с frontend
origins = [
    "https://poolvpn.vercel.app",
    "http://localhost:3000",  # Для локальной разработки
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить все методы (GET, POST и т.д.)
    allow_headers=["*"],  # Разрешить все заголовки
)

# Include routers
app.include_router(auth.router)
app.include_router(spa.router)
app.include_router(vpn.router)


@app.get("/")
def read_root():
    return {"message": "Hello from VPS!"}


@app.get("/health")
async def health_check():
    health = {"status": "ok", "database": "unknown", "storage": "sqlite"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        health["status"] = "degraded"

    return health


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", reload=settings.DEBUG)
