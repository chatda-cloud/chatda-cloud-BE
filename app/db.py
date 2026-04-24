from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


# ── 엔진 ──────────────────────────────────────────────────
# pool_pre_ping=True: 커넥션 재사용 전 유효성 체크 (RDS 재연결 대응)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.ENV == "development"),   # dev 환경에서만 SQL 로깅
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)


# ── 세션 팩토리 ────────────────────────────────────────────
# expire_on_commit=False: 커밋 후에도 인스턴스 속성 접근 가능
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ── Base ───────────────────────────────────────────────────
# 모든 SQLAlchemy 모델이 상속받는 기반 클래스
class Base(DeclarativeBase):
    pass


# ── 세션 의존성 ────────────────────────────────────────────
# FastAPI Depends에서 사용: get_db()
# 요청 단위로 세션을 열고, 성공 시 commit / 예외 시 rollback 자동 처리
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise