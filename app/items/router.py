"""
items 라우터

등록 흐름:
  1. 클라이언트가 Lambda(/presigned-url)로 S3 서명 URL 발급
  2. 클라이언트가 S3에 이미지 직접 PUT 업로드
  3. POST /api/items/lost|found 에 s3Key 포함해서 호출 → DB 저장 후 즉시 응답
  4. 백그라운드: 태깅(Rekognition+CLIP+Gemini) → 매칭 순서로 실행
"""
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, get_db
from app.dependencies import get_current_user
from app.tagging.service import _build_image_url
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
logger = logging.getLogger(__name__)


# ── 백그라운드 태깅 → 매칭 래퍼 ──────────────────────────
# 태깅이 완료된 item_vector가 있어야 매칭이 의미있으므로 순서대로 실행
async def _bg_run_tagging_and_matching(item_id: int, s3_key: str | None, is_lost: bool) -> None:
    from app.tagging.service import process_tags
    from app.matching.service import run_matching

    async with AsyncSessionLocal() as db:
        try:
            await process_tags(item_id=item_id, db=db, s3_key=s3_key)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("백그라운드 태깅 실패 (item_id=%d)", item_id)
            return

    async with AsyncSessionLocal() as db:
        try:
            await run_matching(db, item_id, is_lost=is_lost)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("백그라운드 매칭 실패 (item_id=%d)", item_id)


# ── 분실물 등록 ───────────────────────────────────────────
@router.post(
    "/lost",
    status_code=201,
    summary="분실물 등록",
    description="""분실물을 등록합니다. `s3Key`를 함께 전달하면 응답에 CDN `imageUrl`이 즉시 포함되고, 백그라운드에서 AI 태깅(Rekognition → CLIP → Gemini)이 자동 실행됩니다.\n\n**이미지 업로드 플로우:**\n1. `POST /presigned-url` (Lambda) — s3Key + presignedUrl 발급\n2. `PUT {presignedUrl}` (S3 직접) — 이미지 업로드\n3. 이 엔드포인트에 s3Key 포함해서 호출""",
)
async def create_lost_item_route(
    background_tasks: BackgroundTasks,
    item_name: str = Form(...),
    date_start: datetime = Form(...),
    date_end: datetime = Form(...),
    location: str = Form(...),
    raw_text: str | None = Form(None),
    s3_key: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    body = LostItemCreate(
        item_name=item_name,
        date_start=date_start,
        date_end=date_end,
        location=location,
        raw_text=raw_text,
    )
    data = await create_lost_item(db, current_user.id, body)
    if s3_key:
        data.image_url = _build_image_url(s3_key)
        background_tasks.add_task(_bg_run_tagging_and_matching, data.item_id, s3_key, True)
    return {"success": True, "code": 201, "message": "분실물이 등록되었습니다.", "data": data.model_dump()}


# ── 습득물 등록 ───────────────────────────────────────────
@router.post(
    "/found",
    status_code=201,
    summary="습득물 등록",
    description="""습득물을 등록합니다. `s3Key`를 함께 전달하면 응답에 CDN `imageUrl`이 즉시 포함되고, 백그라운드에서 AI 태깅(Rekognition → CLIP → Gemini)이 자동 실행됩니다.\n\n**이미지 업로드 플로우:**\n1. `POST /presigned-url` (Lambda) — s3Key + presignedUrl 발급\n2. `PUT {presignedUrl}` (S3 직접) — 이미지 업로드\n3. 이 엔드포인트에 s3Key 포함해서 호출""",
)
async def create_found_item_route(
    background_tasks: BackgroundTasks,
    item_name: str = Form(...),
    found_date: datetime = Form(...),
    location: str = Form(...),
    raw_text: str | None = Form(None),
    s3_key: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    body = FoundItemCreate(
        item_name=item_name,
        found_date=found_date,
        location=location,
        raw_text=raw_text,
    )
    data = await create_found_item(db, current_user.id, body)
    if s3_key:
        data.image_url = _build_image_url(s3_key)
        background_tasks.add_task(_bg_run_tagging_and_matching, data.item_id, s3_key, False)
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