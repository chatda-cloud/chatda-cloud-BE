"""
items 라우터

등록 흐름:
  1. 요청 수신
  2. DB 저장 + 태깅 (동기) → 응답 즉시 반환
  3. 매칭 (BackgroundTasks) → 응답과 무관하게 백그라운드 실행
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, get_db
from app.dependencies import get_current_user
from app.items.schema import FoundItemUpdate, LostItemCreate, LostItemUpdate, FoundItemCreate
from app.items.service import (
    create_found_item,
    create_lost_item,
    delete_found_item,
    delete_lost_item,
    read_found_item,
    read_lost_item,
    update_found_item,
    update_lost_item,
)
from app.models import User

router = APIRouter()


# ── 백그라운드 매칭 래퍼 ──────────────────────────────────
# BackgroundTasks는 요청 세션이 닫힌 후 실행되므로
# 별도 세션을 새로 열어서 매칭을 수행해야 함
async def _bg_run_matching(item_id: int, is_lost: bool) -> None:
    from app.matching.service import run_matching
    async with AsyncSessionLocal() as db:
        try:
            await run_matching(db, item_id, is_lost=is_lost)
            await db.commit()
        except Exception:
            await db.rollback()
            import logging
            logging.getLogger(__name__).exception(
                "백그라운드 매칭 실패 (item_id=%d)", item_id
            )


# ── 분실물 등록 ───────────────────────────────────────────
@router.post("/lost", status_code=201)
async def create_lost_item_route(
    background_tasks: BackgroundTasks,
    item_name: str = Form(...),
    date_start: datetime = Form(...),
    date_end: datetime = Form(...),
    location: str = Form(...),
    raw_text: str | None = Form(None),
    image: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image_bytes = await image.read() if image else None
    body = LostItemCreate(
        item_name=item_name,
        date_start=date_start,
        date_end=date_end,
        location=location,
        raw_text=raw_text,
    )
    data = await create_lost_item(db, current_user.id, body, image_bytes)

    # 매칭은 백그라운드에서 별도 세션으로 실행
    background_tasks.add_task(_bg_run_matching, data.item_id, True)

    return {"success": True, "code": 201, "message": "분실물이 등록되었습니다.", "data": data.model_dump()}


# ── 습득물 등록 ───────────────────────────────────────────
@router.post("/found", status_code=201)
async def create_found_item_route(
    background_tasks: BackgroundTasks,
    item_name: str = Form(...),
    found_date: datetime = Form(...),
    location: str = Form(...),
    raw_text: str | None = Form(None),
    image: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image_bytes = await image.read() if image else None
    body = FoundItemCreate(
        item_name=item_name,
        found_date=found_date,
        location=location,
        raw_text=raw_text,
    )
    data = await create_found_item(db, current_user.id, body, image_bytes)

    # 매칭은 백그라운드에서 별도 세션으로 실행
    background_tasks.add_task(_bg_run_matching, data.item_id, False)

    return {"success": True, "code": 201, "message": "습득물이 등록되었습니다.", "data": data.model_dump()}


# ── 단건 조회 ─────────────────────────────────────────────
@router.get("/lost/{item_id}")
async def get_lost_item_route(item_id: int, db: AsyncSession = Depends(get_db)):
    data = await read_lost_item(db, item_id)
    return {"success": True, "code": 200, "message": "분실물 조회 성공", "data": data.model_dump()}


@router.get("/found/{item_id}")
async def get_found_item_route(item_id: int, db: AsyncSession = Depends(get_db)):
    data = await read_found_item(db, item_id)
    return {"success": True, "code": 200, "message": "습득물 조회 성공", "data": data.model_dump()}


# ── 수정 ─────────────────────────────────────────────────
@router.put("/lost/{item_id}")
async def update_lost_item_route(
    item_id: int,
    body: LostItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await update_lost_item(db, item_id, current_user.id, body)
    return {"success": True, "code": 200, "message": "분실물이 수정되었습니다.", "data": data.model_dump()}


@router.put("/found/{item_id}")
async def update_found_item_route(
    item_id: int,
    body: FoundItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await update_found_item(db, item_id, current_user.id, body)
    return {"success": True, "code": 200, "message": "습득물이 수정되었습니다.", "data": data.model_dump()}


# ── 삭제 ─────────────────────────────────────────────────
@router.delete("/lost/{item_id}")
async def delete_lost_item_route(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_lost_item(db, item_id, current_user.id)
    return {"success": True, "code": 200, "message": "분실물이 삭제되었습니다.", "data": None}


@router.delete("/found/{item_id}")
async def delete_found_item_route(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_found_item(db, item_id, current_user.id)
    return {"success": True, "code": 200, "message": "습득물이 삭제되었습니다.", "data": None}