from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
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
    # asyncpg 드라이버 사용 (postgresql+asyncpg://...)
    DATABASE_URL: str

    # 커넥션 풀 설정
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30        # 커넥션 대기 최대 시간(초)
    DB_POOL_RECYCLE: int = 1800      # 커넥션 재사용 주기(초)

    # ── JWT ───────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── AWS ───────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "ap-northeast-2"

    # S3
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRE: int = 3600  # 초 단위

    # SNS (푸시 알림)
    SNS_TOPIC_ARN: str

    # ── AI 서비스 ─────────────────────────────────────────
    GEMINI_API_KEY: str

    # CLIP 모델명 (openai/CLIP)
    CLIP_MODEL_NAME: str = "ViT-B/32"

    # 매칭 임계값
    MATCH_THRESHOLD: float = 0.7
    VECTOR_WEIGHT: float = 0.8
    TAG_WEIGHT: float = 0.2

    # ── validators ────────────────────────────────────────
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use asyncpg driver: "
                "postgresql+asyncpg://user:password@host:port/dbname"
            )
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()