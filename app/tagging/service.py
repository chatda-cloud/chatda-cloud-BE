import asyncio
import io
import logging

import boto3
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME
from app.models import Item
from app.tagging import rekognition, clip, gemini
from app.tagging.schema import TagsResponse

logger = logging.getLogger(__name__)


def _build_image_url(s3_key: str) -> str:
    return f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"


def _download_s3_image(s3_key: str) -> tuple[bytes, PILImage.Image]:
    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    data = obj["Body"].read()
    return data, PILImage.open(io.BytesIO(data)).convert("RGB")


async def process_tags(item_id: int, s3_key: str, db: AsyncSession) -> None:
    try:
        result = await db.execute(select(Item).where(Item.id == item_id))
        item = result.scalars().first()
        if not item:
            logger.warning("process_tags: item %d not found", item_id)
            return

        loop = asyncio.get_running_loop()

        # ── 1. Rekognition → ai_tags ────────────────────────────────────────
        try:
            ai_tags = await loop.run_in_executor(None, rekognition.detect_labels, s3_key)
        except Exception:
            logger.exception("Rekognition 실패 (item_id=%d)", item_id)
            ai_tags = []

        # ── 2. S3 이미지 다운로드 (CLIP + Gemini 공용) ──────────────────────
        image_bytes: bytes | None = None
        image_pil: PILImage.Image | None = None
        try:
            image_bytes, image_pil = await loop.run_in_executor(None, _download_s3_image, s3_key)
        except Exception:
            logger.exception("S3 이미지 다운로드 실패 (item_id=%d), 텍스트 fallback", item_id)

        # ── 3. CLIP → item_vector (이미지 우선, 텍스트 fallback) ─────────────
        item_vector: list[float] | None = None
        try:
            if image_pil:
                item_vector = await loop.run_in_executor(None, clip.encode_image_from_pil, image_pil)
            else:
                text = f"{item.category or ''} {item.raw_text or ''}".strip()
                if text:
                    item_vector = await loop.run_in_executor(None, clip.encode_text, text)
        except Exception:
            logger.exception("CLIP 인코딩 실패 (item_id=%d)", item_id)

        # ── 4. Gemini → 구조화 태그 (이미지 우선, 텍스트 fallback) ──────────
        gemini_result: dict | None = None
        if image_bytes:
            try:
                gemini_result = await loop.run_in_executor(
                    None, gemini.extract_from_image, image_bytes
                )
            except Exception:
                logger.exception("Gemini 이미지 분석 실패 (item_id=%d)", item_id)

        if gemini_result is None and item.raw_text:
            try:
                gemini_result = await loop.run_in_executor(
                    None, gemini.extract_from_text, item.raw_text
                )
            except Exception:
                logger.exception("Gemini 텍스트 분석 실패 (item_id=%d)", item_id)

        # ── 5. Rekognition + Gemini 태그 병합 ───────────────────────────────
        if gemini_result:
            gemini_tags = gemini_result.get("color", []) + gemini_result.get("features", [])
            ai_tags = list(dict.fromkeys(ai_tags + gemini_tags))

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
        raise HTTPException(status_code=404, detail={
            "success": False, "code": 404,
            "message": "아이템을 찾을 수 없습니다.", "data": None,
        })

    return TagsResponse(
        item_id=item_id,
        category=item.category,
        ai_tags=item.ai_tags or [],
        has_vector=getattr(item, "item_vector", None) is not None,
        image_url=item.image_url,
    )
