"""
users 라우터

  GET   /api/users/me                → 내 정보 조회
  PATCH /api/users/me/username       → 닉네임 변경
  PATCH /api/users/me/profile-image  → 프로필 사진 변경
  GET   /api/users/me/lost-items     → 내 분실물 조회
  GET   /api/users/me/found-items    → 내 습득물 조회
  GET   /api/users/me/matches        → 내 매칭 리스트 조회
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CDN_BASE_URL, S3_BUCKET_NAME, AWS_REGION
from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.users.schema import (
    FoundItemSummary,
    LostItemSummary,
    MatchedItemInfo,
    MatchSummary,
    UpdateProfileImageRequest,
    UpdateUsernameRequest,
    UserOut,
)
from app.users.service import (
    get_my_found_items,
    get_my_lost_items,
    get_my_matches,
    update_profile_image,
    update_username,
)

router = APIRouter()


# ── 내 정보 조회 ──────────────────────────────────────────
@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "success": True,
        "code": 200,
        "message": "내 정보 조회 성공",
        "data": UserOut.model_validate(current_user).model_dump(),
    }


# ── 닉네임 변경 ───────────────────────────────────────────
@router.patch("/me/username")
async def patch_username(
    body: UpdateUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.username.strip():
        raise HTTPException(status_code=400, detail={
            "success": False, "code": 400, "message": "닉네임을 입력해주세요.", "data": None,
        })
    user = await update_username(db, current_user, body.username)
    return {
        "success": True,
        "code": 200,
        "message": "닉네임 변경 성공",
        "data": UserOut.model_validate(user).model_dump(),
    }


# ── 프로필 사진 변경 ──────────────────────────────────────
@router.patch("/me/profile-image")
async def patch_profile_image(
    body: UpdateProfileImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image_url = body.profile_image_url
    if CDN_BASE_URL:
        s3_prefix = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/"
        if image_url.startswith(s3_prefix):
            image_url = image_url.replace(s3_prefix, f"https://{CDN_BASE_URL}/", 1)
    user = await update_profile_image(db, current_user, image_url)
    return {
        "success": True,
        "code": 200,
        "message": "프로필 사진 변경 성공",
        "data": UserOut.model_validate(user).model_dump(),
    }


# ── 내 분실물 조회 ────────────────────────────────────────
@router.get("/me/lost-items")
async def get_my_lost_items_route(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lost_items = await get_my_lost_items(db, current_user.id)
    data = [
        LostItemSummary(
            item_id=li.item_id,
            item_name=li.item_name,  
            category=li.item.category,
            status=li.item.status,
            location=li.location,
            date_start=li.date_start,
            date_end=li.date_end,
            raw_text=li.raw_text,
            image_url=li.image_url,
            created_at=li.item.created_at,
        ).model_dump()
        for li in lost_items
    ]
    return {"success": True, "code": 200, "message": "내 분실물 조회 성공", "data": data}


# ── 내 습득물 조회 ────────────────────────────────────────
@router.get("/me/found-items")
async def get_my_found_items_route(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    found_items = await get_my_found_items(db, current_user.id)
    data = [
        FoundItemSummary(
            item_id=fi.item_id,
            item_name=fi.item_name,
            category=fi.item.category,
            status=fi.item.status,
            location=fi.location,
            found_date=fi.found_date,
            raw_text=fi.raw_text,
            image_url=fi.image_url,
            created_at=fi.item.created_at,
        ).model_dump()
        for fi in found_items
    ]
    return {"success": True, "code": 200, "message": "내 습득물 조회 성공", "data": data}


# ── 내 매칭 리스트 조회 ───────────────────────────────────
@router.get("/me/matches")
async def get_my_matches_route(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    matches = await get_my_matches(db, current_user.id)
    data = []
    for m in matches:
        lost_info = None
        found_info = None
        if m.lost_item and m.lost_item.lost_item:
            li = m.lost_item.lost_item
            lost_info = MatchedItemInfo(
                item_id=li.item_id,
                item_name=li.item_name,
                category=m.lost_item.category,
                image_url=li.image_url,
                location=li.location,
            )
        if m.found_item and m.found_item.found_item:
            fi = m.found_item.found_item
            found_info = MatchedItemInfo(
                item_id=fi.item_id,
                item_name=fi.item_name,
                category=m.found_item.category,
                image_url=fi.image_url,
                location=fi.location,
            )
        data.append(MatchSummary(
            id=m.id,
            lost_item_id=m.lost_item_id,
            found_item_id=m.found_item_id,
            similarity_score=m.similarity_score,
            is_confirmed=m.is_confirmed,
            created_at=m.created_at,
            lost_item=lost_info,
            found_item=found_info,
        ).model_dump())
    return {"success": True, "code": 200, "message": "매칭 리스트 조회 성공", "data": data}