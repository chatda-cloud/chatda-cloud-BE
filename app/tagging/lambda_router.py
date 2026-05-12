from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.tagging.schema import PresignedUrlRequest, PresignedUrlResponse

router = APIRouter()

_FLOW = """
**이미지 업로드 4단계 플로우:**

1. **`POST /presigned-url`** (이 엔드포인트, Lambda) — 서명 URL + s3Key 수령
2. `PUT {presignedUrl}` (S3 직접) — 이미지 바이너리 업로드. Content-Type은 발급 시 지정한 값과 일치해야 함
3. `POST /api/items/{itemId}/process-tags` (ECS) — s3Key 전달, 백그라운드 AI 태깅 시작
4. `GET /api/items/{itemId}/tags` (ECS) — 태깅 결과 조회

> ⚠️ 이 엔드포인트는 **AWS Lambda**에서 실행됩니다. FastAPI 서버가 아닌 Lambda 함수 URL 또는 API Gateway를 통해 호출하세요.
"""


@router.post(
    "/presigned-url",
    response_model=PresignedUrlResponse,
    response_model_by_alias=True,
    summary="S3 업로드용 서명 URL 발급",
    description=_FLOW,
    response_description="서명된 S3 PUT URL, S3 객체 키, 유효 시간",
    tags=["Upload (Lambda)"],
)
async def presigned_url_stub(body: PresignedUrlRequest):
    """문서 전용 스텁 — 실제 처리는 AWS Lambda에서 수행됩니다."""
    return JSONResponse(
        status_code=501,
        content={"message": "이 엔드포인트는 AWS Lambda에서 처리됩니다."},
    )
