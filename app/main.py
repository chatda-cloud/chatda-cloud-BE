import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import engine, Base
from app.models import Base
import app.models

from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.items.router import router as items_router
from app.tagging.router import router as tagging_router
from app.tagging.lambda_router import router as lambda_docs_router
from app.matching.router import router as matching_router

logging.basicConfig(level=logging.INFO)
settings = get_settings()


# ── 앱 수명주기 ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: DB 테이블 생성 (개발 환경) / 프로덕션에선 Alembic 사용
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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
app.include_router(lambda_docs_router, tags=["Upload (Lambda)"])
app.include_router(matching_router, prefix=f"{API_PREFIX}", tags=["Matching"])


# ── 전역 예외 처리 ─────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "code": 500, "message": str(exc), "data": None},
    )


# ── 헬스체크 ───────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "env": settings.ENV}
