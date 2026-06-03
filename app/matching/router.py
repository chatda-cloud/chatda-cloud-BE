"""
matching 라우터

  GET   /api/items/lost/{item_id}/similarity  → 분실물 기준 유사 습득물 목록
  POST  /api/items/lost/{item_id}/match       → 매칭 수동 실행
  PATCH /api/matches/{match_id}/confirm       → 매칭 확정
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.matching.schema import MatchConfirmRequest, MatchListResponse, MatchResponse
from app.matching.service import confirm_match, get_matches_by_lost_item, run_matching
from app.models import User

router = APIRouter()


@router.get("/items/lost/{item_id}/similarity", response_model=MatchListResponse)
async def get_similarity(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    matches = await get_matches_by_lost_item(db, item_id)
    return MatchListResponse(
        total=len(matches),
        matches=[MatchResponse.model_validate(m) for m in matches],
    )


@router.post("/items/lost/{item_id}/match", status_code=202)
async def trigger_matching(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """매칭 수동 실행 (태깅 완료 후 호출)."""
    matches = await run_matching(db, item_id)
    return {
        "success": True,
        "code": 202,
        "message": f"매칭 완료. {len(matches)}건 저장됨.",
        "data": {"matched_count": len(matches)},
    }


@router.patch("/matches/{match_id}/confirm")
async def confirm_match_route(
    match_id: int,
    body: MatchConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not body.is_confirmed:
        raise HTTPException(status_code=400, detail={
            "success": False, "code": 400,
            "message": "is_confirmed는 true만 허용됩니다.", "data": None,
        })

    match = await confirm_match(db, match_id, current_user.id)
    if not match:
        raise HTTPException(status_code=404, detail={
            "success": False, "code": 404,
            "message": "매칭을 찾을 수 없습니다.", "data": None,
        })

    return {
        "success": True,
        "code": 200,
        "message": "매칭이 확정되었습니다.",
        "data": MatchResponse.model_validate(match).model_dump(),
    }