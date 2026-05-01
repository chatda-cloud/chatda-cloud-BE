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

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.users.schema import (
    ItemSummary,
    MatchSummary,
    UpdateProfileImageRequest,
    UpdateUsernameRequest,
    UserOut,
)
from app.users.service import (
    get_found_items,
    get_lost_items,
    get_matches,
    update_profile_image,
    update_username,
)

router = APIRouter(tags=["users"])


def _user_out(user: User) -> dict:
    return UserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        gender=user.gender,
        birthDate=user.birthdate,
        profileImage=user.profile_image_url,
        createdAt=user.created_at,
    ).model_dump()


# ── 내 정보 조회 ──────────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"success": True, "code": 200, "message": "내 정보 조회 성공",
            "data": _user_out(current_user)}


# ── 닉네임 변경 ───────────────────────────────────────────────────────────────

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
    return {"success": True, "code": 200, "message": "닉네임 변경 성공",
            "data": _user_out(user)}


# ── 프로필 사진 변경 ──────────────────────────────────────────────────────────

@router.patch("/me/profile-image")
async def patch_profile_image(
    body: UpdateProfileImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await update_profile_image(db, current_user, body.profileImage)
    return {"success": True, "code": 200, "message": "프로필 사진 변경 성공",
            "data": _user_out(user)}


# ── 내 분실물 조회 ────────────────────────────────────────────────────────────

@router.get("/me/lost-items")
async def get_my_lost_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await get_lost_items(db, current_user.id)
    data = [
        ItemSummary(
            id=it.id, itemType=it.item_type, category=it.category,
            rawText=it.raw_text, imageUrl=it.image_url,
            status=it.status, createdAt=it.created_at,
        ).model_dump()
        for it in items
    ]
    return {"success": True, "code": 200, "message": "내 분실물 조회 성공", "data": data}


# ── 내 습득물 조회 ────────────────────────────────────────────────────────────

@router.get("/me/found-items")
async def get_my_found_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await get_found_items(db, current_user.id)
    data = [
        ItemSummary(
            id=it.id, itemType=it.item_type, category=it.category,
            rawText=it.raw_text, imageUrl=it.image_url,
            status=it.status, createdAt=it.created_at,
        ).model_dump()
        for it in items
    ]
    return {"success": True, "code": 200, "message": "내 습득물 조회 성공", "data": data}


# ── 내 매칭 리스트 조회 ───────────────────────────────────────────────────────

@router.get("/me/matches")
async def get_my_matches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    matches = await get_matches(db, current_user.id)
    data = [
        MatchSummary(
            id=m.id, lostItemId=m.lost_item_id, foundItemId=m.found_item_id,
            similarity=m.similarity, status=m.status, createdAt=m.created_at,
        ).model_dump()
        for m in matches
    ]
    return {"success": True, "code": 200, "message": "매칭 리스트 조회 성공", "data": data}
