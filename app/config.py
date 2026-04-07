from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    BASE_DIR: Path = Path(__file__).resolve().parents[1]
    REPO_DIR: Path = Path(__file__).resolve().parents[2]

    # SQLite
    SQLITE_PATH: str = str(Path(__file__).resolve().parents[1] / "vpn_app.db")

    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # XUI Panel
    XUI_HOST: str = "https://194.87.25.149:21346/0jfNLyvtF2tTBZV1v5"
    XUI_USERNAME: str = "admin"
    
    XUI_PASSWORD: str = "admin"
    VPN_LINK_REMARK: str = "KRUTOY_VPN"
    VPN_PUBLIC_HOST: str = "194.87.25.149"
    VPN_PUBLIC_PORT: int = 443
    VPN_NETWORK: str = "grpc"
    VPN_SERVICE_NAME: str = ""
    VPN_AUTHORITY: str = ""
    VPN_SECURITY: str = "reality"
    VPN_PBK: str = ""
    VPN_FP: str = "chrome"
    VPN_SNI: str = ""
    VPN_SID: str = ""
    VPN_SPX: str = "/"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = "8548738879:AAG17FwYiajZp8jNHkovGxL3Ro24OIAasqE"

    # App
    APP_NAME: str = "VPN Key Manager"
    DEBUG: bool = True
    LOGIN_CODE_EXPIRE_MINUTES: int = 10
    EMAIL_DEV_LOG_ONLY: bool = True

    # SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Avara VPN"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("SMTP_USE_TLS", "SMTP_USE_SSL", "EMAIL_DEV_LOG_ONLY", mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @property
    def DATABASE_URL(self) -> str:
        db_path = Path(self.SQLITE_PATH)
        if not db_path.is_absolute():
            db_path = self.REPO_DIR / db_path
        return f"sqlite+aiosqlite:///{db_path.resolve().as_posix()}"

    @property
    def FRONTEND_DIST_DIR(self) -> Path:
        return self.REPO_DIR / "frontend" / "POOLVPN" / "dist"

    @property
    def EMAIL_DELIVERY_ENABLED(self) -> bool:
        return bool(
            self.SMTP_HOST
            and self.SMTP_PORT
            and self.SMTP_FROM_EMAIL
        )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
