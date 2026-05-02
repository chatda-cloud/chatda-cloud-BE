"""
items 라우터

  POST   /api/items/lost              → 분실물 등록
  POST   /api/items/found             → 습득물 등록
  GET    /api/items/lost/{item_id}    → 분실물 단건 조회
  GET    /api/items/found/{item_id}   → 습득물 단건 조회
  PUT    /api/items/lost/{item_id}    → 분실물 수정
  PUT    /api/items/found/{item_id}   → 습득물 수정
  DELETE /api/items/lost/{item_id}    → 분실물 삭제
  DELETE /api/items/found/{item_id}   → 습득물 삭제
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.items.schema import FoundItemCreate, FoundItemUpdate, LostItemCreate, LostItemUpdate
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


@router.post("/lost", status_code=201)
async def create_lost_item_route(
    body: LostItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await create_lost_item(db, current_user.id, body)
    return {"success": True, "code": 201, "message": "분실물이 등록되었습니다.", "data": data.model_dump()}


@router.post("/found", status_code=201)
async def create_found_item_route(
    body: FoundItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await create_found_item(db, current_user.id, body)
    return {"success": True, "code": 201, "message": "습득물이 등록되었습니다.", "data": data.model_dump()}


@router.get("/lost/{item_id}")
async def get_lost_item_route(
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    data = await read_lost_item(db, item_id)
    return {"success": True, "code": 200, "message": "분실물 조회 성공", "data": data.model_dump()}


@router.get("/found/{item_id}")
async def get_found_item_route(
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    data = await read_found_item(db, item_id)
    return {"success": True, "code": 200, "message": "습득물 조회 성공", "data": data.model_dump()}


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


@router.post("/presigned-url")
async def create_presigned_url_placeholder(
    current_user: User = Depends(get_current_user),
):
    # S3 이미지 업로드 플로우 연결 예정
    _ = current_user
    raise HTTPException(
        status_code=501,
        detail={
            "success": False,
            "code": 501,
            "message": "이미지 업로드 연결은 다음 단계에서 구현 예정입니다.",
            "data": None,
        },
    )