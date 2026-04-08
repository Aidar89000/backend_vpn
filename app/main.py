from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.config import get_settings
from app.database import engine, init_db
from app.routers import auth, spa, vpn
from app.services.telegram_bot import start_bot, stop_bot

settings = get_settings()
frontend_dist = settings.FRONTEND_DIST_DIR


# Custom Jinja2 filters
def setup_template_filters(templates: Jinja2Templates):
    """Setup custom filters for Jinja2 templates."""
    
    @templates.env.filter
    def timestamp_to_date(timestamp_ms):
        """Convert millisecond timestamp to readable date."""
        if not timestamp_ms or timestamp_ms == 0:
            return "Бессрочно"
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            return dt.strftime('%d.%m.%Y %H:%M')
        except Exception:
            return "Неизвестно"
    
    templates.env.filters['timestamp_to_date'] = timestamp_to_date


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
    description="VPN Key Manager with integrated frontend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(spa.router)
app.include_router(vpn.router)

if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


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


def _frontend_file(path: str) -> Path | None:
    candidate = frontend_dist / path
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


@app.get("/", response_class=HTMLResponse)
async def spa_index():
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        "<h1>Frontend build not found</h1><p>Run npm run build in frontend/POOLVPN.</p>",
        status_code=503,
    )


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "auth/", "vpn/", "health")):
        raise HTTPException(status_code=404)

    static_file = _frontend_file(full_path)
    if static_file:
        return FileResponse(static_file)

    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", reload=settings.DEBUG)
