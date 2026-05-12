from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.tagging.schema import ProcessTagsRequest, TagsResponse
from app.tagging import service

router = APIRouter()

_UPLOAD_FLOW = """
이미지 업로드는 클라이언트가 S3에 직접 수행합니다. 순서:

1. `POST /presigned-url` (Lambda) — 서명 URL + s3Key 수령
2. `PUT {presignedUrl}` (S3 직접) — 이미지 바이너리 업로드
3. **`POST /api/items/{itemId}/process-tags`** (이 엔드포인트) — s3Key 전달
4. `GET /api/items/{itemId}/tags` — 태깅 결과 조회
"""


@router.post(
    "/{item_id}/process-tags",
    status_code=202,
    summary="AI 태깅 요청",
    description=f"""S3 업로드 완료 후 호출합니다. 태깅은 백그라운드에서 실행되며 즉시 202를 반환합니다.

태깅 파이프라인: **Rekognition → CLIP(이미지 벡터) → Gemini(category + features) → DB 저장**
실패해도 아이템 등록에 영향 없습니다.

{_UPLOAD_FLOW}""",
    response_description="태깅 파이프라인 시작 확인 (처리는 백그라운드에서 진행)",
)
async def process_tags(
    item_id: int,
    body: ProcessTagsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    background_tasks.add_task(service.process_tags, item_id, body.s3_key, db)
    return {"success": True, "message": "태깅 처리가 시작되었습니다."}


@router.get(
    "/{item_id}/tags",
    response_model=TagsResponse,
    response_model_by_alias=True,
    summary="AI 태깅 결과 조회",
    description="해당 아이템의 AI 태깅 결과를 반환합니다. `process-tags` 호출 후 파이프라인이 완료되어야 값이 채워집니다.",
    response_description="카테고리, 특징 키워드, 벡터 임베딩 완료 여부, 이미지 URL",
)
async def get_tags(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await service.get_item_tags(item_id, db)
