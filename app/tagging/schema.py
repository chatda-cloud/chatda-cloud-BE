from pydantic import BaseModel, Field


class PresignedUrlRequest(BaseModel):
    item_id: int = Field(..., alias="itemId", description="아이템 ID")
    filename: str = Field(..., description="업로드할 파일명 (예: jacket.jpg)")
    content_type: str = Field("image/jpeg", alias="contentType", description="MIME 타입")

    model_config = {"populate_by_name": True}


class PresignedUrlResponse(BaseModel):
    presigned_url: str = Field(..., alias="presignedUrl", description="PUT 요청에 사용할 서명된 S3 URL (5분간 유효)")
    s3_key: str = Field(..., alias="s3Key", description="S3 객체 키 — process-tags 호출 시 그대로 전달")
    expires_in: int = Field(300, alias="expiresIn", description="URL 유효 시간 (초)")

    model_config = {"populate_by_name": True}


class ProcessTagsRequest(BaseModel):
    s3_key: str = Field(..., alias="s3Key", description="Step 1(presigned-url)에서 수령한 S3 객체 키")

    model_config = {"populate_by_name": True}


class TagsResponse(BaseModel):
    item_id: int = Field(..., alias="itemId", description="아이템 ID")
    category: str | None = Field(None, description="AI가 분류한 카테고리")
    features: list[str] = Field(..., alias="features", description="색상·형태·특이사항 등 특징 키워드 목록")
    has_vector: bool = Field(..., alias="hasVector", description="CLIP 벡터 임베딩 완료 여부")
    image_url: str | None = Field(None, alias="imageUrl", description="S3 이미지 URL")

    model_config = {"populate_by_name": True}
