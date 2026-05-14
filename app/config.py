from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── 앱 ────────────────────────────────────────────────
    ENV: Literal["development", "staging", "production"] = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ── 데이터베이스 ──────────────────────────────────────
    DATABASE_URL: str = ""
    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_NAME: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # ── JWT ───────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── AWS ───────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRE: int = 3600
    SNS_TOPIC_ARN: str

    # ── AI ────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    CLIP_MODEL_NAME: str = "ViT-B/32"
    MATCH_THRESHOLD: float = 0.7
    VECTOR_WEIGHT: float = 0.8
    TAG_WEIGHT: float = 0.2

    # ── SMTP (비밀번호 재설정 이메일) ──────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER: str = ""
    PW_RESET_BASE_URL: str = "http://localhost:3000/reset-password"

    # ── validators ────────────────────────────────────────
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v:
            return v
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use asyncpg driver: "
                "postgresql+asyncpg://user:password@host:port/dbname"
            )
        return v

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if all([self.DB_HOST, self.DB_NAME, self.DB_USER, self.DB_PASSWORD]):
            return (
                f"postgresql+asyncpg://{quote_plus(self.DB_USER)}:"
                f"{quote_plus(self.DB_PASSWORD)}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        raise ValueError("DATABASE_URL or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD must be set")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# ── auth service에서 직접 임포트하는 변수들 ────────────────
# service.py에서 get_settings() 대신 바로 쓸 수 있도록 제공
_s = get_settings()

JWT_SECRET = _s.SECRET_KEY
JWT_ALGORITHM = _s.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = _s.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = _s.REFRESH_TOKEN_EXPIRE_DAYS

SMTP_HOST = _s.SMTP_HOST
SMTP_PORT = _s.SMTP_PORT
SMTP_USER = _s.SMTP_USER
SMTP_PASSWORD = _s.SMTP_PASSWORD
SMTP_SENDER = _s.SMTP_SENDER
PW_RESET_BASE_URL = _s.PW_RESET_BASE_URL

# ── tagging service에서 직접 임포트하는 변수들 ───────────────
GEMINI_API_KEY = _s.GEMINI_API_KEY
AWS_ACCESS_KEY_ID = _s.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = _s.AWS_SECRET_ACCESS_KEY
AWS_REGION = _s.AWS_REGION
S3_BUCKET_NAME = _s.S3_BUCKET_NAME

DATABASE_URL = _s.database_url
SNS_TOPIC_ARN = _s.SNS_TOPIC_ARN
