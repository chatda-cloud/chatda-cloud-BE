from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import engine, Base
import app.models

# ── 라우터 임포트 ──────────────────────────────────────────
from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.items.router import router as items_router
from app.tagging.router import router as tagging_router
from app.matching.router import router as matching_router

settings = get_settings()


# ── 앱 수명주기 ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: DB 테이블 생성 (개발 환경) / 프로덕션에선 Alembic 사용
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # shutdown: 커넥션 풀 정리
    await engine.dispose()


# ── 앱 초기화 ──────────────────────────────────────────────
app = FastAPI(
    title="Chatda Lost & Found API",
    version="1.0.0",
    description="AI 기반 캠퍼스 분실물 스마트 매칭 플랫폼",
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url="/redoc" if settings.ENV != "production" else None,
    lifespan=lifespan,
)


# ── CORS ───────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 라우터 등록 ────────────────────────────────────────────
API_PREFIX = "/api"

app.include_router(auth_router,     prefix=f"{API_PREFIX}/auth",    tags=["Auth"])
app.include_router(users_router,    prefix=f"{API_PREFIX}/users",   tags=["Users"])
app.include_router(items_router,    prefix=f"{API_PREFIX}/items",   tags=["Items"])
app.include_router(tagging_router,  prefix=f"{API_PREFIX}/items",   tags=["Tagging"])
app.include_router(matching_router, prefix=f"{API_PREFIX}/items",   tags=["Matching"])


# ── 헬스체크 ───────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "env": settings.ENV}