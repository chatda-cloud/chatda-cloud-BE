import asyncio
import io
import logging

import boto3
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME
from app.models import Item
from app.tagging import rekognition, clip
from app.tagging.schema import TagsResponse

logger = logging.getLogger(__name__)


def _build_image_url(s3_key: str) -> str:
    return f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"


async def process_tags(item_id: int, s3_key: str, db: AsyncSession) -> None:
    try:
        result = await db.execute(select(Item).where(Item.id == item_id))
        item = result.scalars().first()
        if not item:
            logger.warning("process_tags: item %d not found", item_id)
            return

        loop = asyncio.get_event_loop()

        # Rekognition → ai_tags
        try:
            ai_tags = await loop.run_in_executor(None, rekognition.detect_labels, s3_key)
        except Exception:
            logger.exception("Rekognition 실패 (item_id=%d)", item_id)
            ai_tags = []

        # CLIP 이미지 인코딩 시도, 실패 시 텍스트 인코딩으로 fallback
        item_vector: list[float] | None = None
        try:
            s3 = boto3.client(
                "s3",
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            )
            def _download_and_encode() -> list[float]:
                obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
                image = PILImage.open(io.BytesIO(obj["Body"].read())).convert("RGB")
                return clip.encode_image_from_pil(image)

            item_vector = await loop.run_in_executor(None, _download_and_encode)
        except Exception:
            logger.exception("CLIP 이미지 인코딩 실패 (item_id=%d), 텍스트로 fallback", item_id)
            try:
                raw_text = item.raw_text or ""
                category = item.category or ""
                text = f"{category} {raw_text}".strip()
                if text:
                    item_vector = await loop.run_in_executor(None, clip.encode_text, text)
            except Exception:
                logger.exception("CLIP 텍스트 인코딩도 실패 (item_id=%d)", item_id)

        item.ai_tags = ai_tags
        item.item_vector = item_vector
        item.image_url = _build_image_url(s3_key)

        await db.commit()
        logger.info("태깅 완료 (item_id=%d, tags=%s)", item_id, ai_tags)

    except Exception:
        logger.exception("process_tags 예외 (item_id=%d)", item_id)
        await db.rollback()


async def get_item_tags(item_id: int, db: AsyncSession) -> TagsResponse:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalars().first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"success": False, "code": 404, "message": "아이템을 찾을 수 없습니다.", "data": None})

    return TagsResponse(
        item_id=item_id,
        category=item.category,
        ai_tags=item.ai_tags or [],
        has_vector=getattr(item, "item_vector", None) is not None,
        image_url=item.image_url,
    )
