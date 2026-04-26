from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    ENV: str = "development"
    CORS_ORIGINS: list[str] = ["*"]

    # DB
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/chatda"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PW_RESET_BASE_URL: str = ""

    # AWS
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str = ""

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER: str = ""

    # AI
    GEMINI_API_KEY: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


# 모듈 레벨 변수 (기존 코드 호환)
_s = get_settings()
DATABASE_URL = _s.DATABASE_URL
JWT_SECRET = _s.JWT_SECRET
JWT_ALGORITHM = _s.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = _s.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = _s.REFRESH_TOKEN_EXPIRE_DAYS
PW_RESET_BASE_URL = _s.PW_RESET_BASE_URL
AWS_ACCESS_KEY_ID = _s.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = _s.AWS_SECRET_ACCESS_KEY
AWS_REGION = _s.AWS_REGION
S3_BUCKET_NAME = _s.S3_BUCKET_NAME
SMTP_HOST = _s.SMTP_HOST
SMTP_PORT = _s.SMTP_PORT
SMTP_USER = _s.SMTP_USER
SMTP_PASSWORD = _s.SMTP_PASSWORD
SMTP_SENDER = _s.SMTP_SENDER
GEMINI_API_KEY = _s.GEMINI_API_KEY
