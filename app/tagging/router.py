from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.tagging.schema import ProcessTagsRequest, TagsResponse
from app.tagging import service

router = APIRouter()


@router.get("/{item_id}/tags", response_model=TagsResponse, response_model_by_alias=True)
async def get_tags(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await service.get_item_tags(item_id, db)


@router.post("/{item_id}/process-tags", status_code=202)
async def process_tags(
    item_id: int,
    body: ProcessTagsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    background_tasks.add_task(service.process_tags, item_id, body.s3_key, db)
    return {"success": True, "message": "태깅 처리가 시작되었습니다."}
