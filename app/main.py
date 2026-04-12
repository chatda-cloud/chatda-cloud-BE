import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth.router import router as auth_router
from app.db import engine
from app.models import Base
from app.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
# from app.items.router import router as items_router       # TODO: 담당자 B
# from app.tagging.router import router as tagging_router   # TODO: 담당자 C
# from app.matching.router import router as matching_router # TODO: 담당자 D

app = FastAPI(title="Chatda Backend", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(users_router)
# app.include_router(items_router)
# app.include_router(tagging_router)
# app.include_router(matching_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "code": 500, "message": str(exc), "data": None},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
