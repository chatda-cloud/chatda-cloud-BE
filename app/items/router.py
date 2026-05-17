"""
등록(분실물·습득물)은 메타데이터만 저장합니다. 이미지는 presigned URL로 S3에 직접 업로드합니다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.items.schema import (
    FoundItemCreate,
    FoundItemUpdate,
    LostItemCreate,
    LostItemUpdate,
)
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

_UPLOAD_FLOW = """ """


# ── 분실물 등록 ───────────────────────────────────────────
@router.post(
    "/lost",
    status_code=201,
    summary="분실물 등록",
    description=f"""분실물 메타데이터를 저장합니다. 이미지는 서버로 전송하지 않습니다.

{_UPLOAD_FLOW}""",
)
async def create_lost_item_route(
    body: LostItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await create_lost_item(db, current_user.id, body, image_bytes=None)
    return {
        "success": True,
        "code": 201,
        "message": "분실물이 등록되었습니다. 이미지가 있으면 presigned URL 업로드 후 process-tags를 호출하세요.",
        "data": data.model_dump(),
    }


# ── 습득물 등록 ───────────────────────────────────────────
@router.post(
    "/found",
    status_code=201,
    summary="습득물 등록",
    description=f"""습득물 메타데이터를 저장합니다. 이미지는 서버로 전송하지 않습니다.

{_UPLOAD_FLOW}""",
)
async def create_found_item_route(
    body: FoundItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await create_found_item(db, current_user.id, body, image_bytes=None)
    return {
        "success": True,
        "code": 201,
        "message": "습득물이 등록되었습니다. 이미지가 있으면 presigned URL 업로드 후 process-tags를 호출하세요.",
        "data": data.model_dump(),
    }


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