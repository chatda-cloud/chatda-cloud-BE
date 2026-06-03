from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.tagging.schema import TagsResponse
from app.tagging import service

router = APIRouter()


@router.get(
    "/{item_id}/tags",
    response_model=TagsResponse,
    response_model_by_alias=True,
    summary="AI 태깅 결과 조회",
    description="해당 아이템의 AI 태깅 결과를 반환합니다. 아이템 등록(POST /api/items/lost|found) 시 s3Key를 함께 전달하면 백그라운드 태깅 파이프라인이 자동 실행되며, 완료 후 값이 채워집니다.",
    response_description="카테고리, 특징 키워드, 벡터 임베딩 완료 여부, 이미지 URL",
)
async def get_tags(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await service.get_item_tags(item_id, db)
