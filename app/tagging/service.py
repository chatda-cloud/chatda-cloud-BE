import asyncio
import io
import logging

import boto3
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME
from app.models import FoundItem, Item, ItemStatus, LostItem
from app.tagging import clip, gemini, rekognition
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


async def _get_detail(db: AsyncSession, item: Item) -> LostItem | FoundItem | None:
    """Item의 status에 따라 LostItem 또는 FoundItem 반환."""
    if item.status == ItemStatus.LOST:
        result = await db.execute(select(LostItem).where(LostItem.item_id == item.id))
        return result.scalars().first()
    else:
        result = await db.execute(select(FoundItem).where(FoundItem.item_id == item.id))
        return result.scalars().first()


async def process_tags(item_id: int, s3_key: str, db: AsyncSession) -> None:
    """
    백그라운드 태깅 파이프라인.
    Rekognition → S3 다운로드 → CLIP → Gemini → DB 저장
    ai_tags / item_vector / image_url / category는 LostItem 또는 FoundItem에 저장.
    """
    try:
        # ── Item 조회 ──────────────────────────────────────
        result = await db.execute(select(Item).where(Item.id == item_id))
        item = result.scalars().first()
        if not item:
            logger.warning("process_tags: item %d not found", item_id)
            return

        detail = await _get_detail(db, item)
        if not detail:
            logger.warning("process_tags: detail not found for item %d", item_id)
            return

        loop = asyncio.get_running_loop()

        # ── 1. Rekognition → 힌트 라벨 ────────────────────
        try:
            rek_labels = await loop.run_in_executor(None, rekognition.detect_labels, s3_key)
        except Exception:
            logger.exception("Rekognition 실패 (item_id=%d)", item_id)
            rek_labels = []

        # ── 2. S3 이미지 다운로드 ─────────────────────────
        image_bytes: bytes | None = None
        image_pil: PILImage.Image | None = None
        try:
            image_bytes, image_pil = await loop.run_in_executor(None, _download_s3_image, s3_key)
        except Exception:
            logger.exception("S3 다운로드 실패 (item_id=%d), 텍스트 fallback", item_id)

        # ── 3. CLIP → item_vector ─────────────────────────
        item_vector: list[float] | None = None
        try:
            if image_pil:
                item_vector = await loop.run_in_executor(None, clip.encode_image_from_pil, image_pil)
            else:
                text = f"{item.category or ''} {detail.raw_text or ''}".strip()
                if text:
                    item_vector = await loop.run_in_executor(None, clip.encode_text, text)
        except Exception:
            logger.exception("CLIP 인코딩 실패 (item_id=%d)", item_id)

        # ── 4. Gemini → 구조화 태그 ───────────────────────
        gemini_result: dict | None = None
        if image_bytes:
            try:
                gemini_result = await loop.run_in_executor(
                    None,
                    gemini.extract_from_image,
                    image_bytes,
                    rek_labels or None,
                    detail.raw_text or None,
                )
            except Exception:
                logger.exception("Gemini 이미지 분석 실패 (item_id=%d)", item_id)

        if gemini_result is None and detail.raw_text:
            try:
                gemini_result = await loop.run_in_executor(
                    None, gemini.extract_from_text, detail.raw_text
                )
            except Exception:
                logger.exception("Gemini 텍스트 분석 실패 (item_id=%d)", item_id)

        # ── 5. 최종 저장 ──────────────────────────────────
        # category → Item 테이블
        # ai_tags / item_vector / image_url → LostItem 또는 FoundItem 테이블
        ai_tags: list[str] = []
        if gemini_result:
            ai_tags = gemini_result.get("color", []) + gemini_result.get("features", [])
            item.category = gemini_result.get("category") or item.category

        detail.ai_tags = ai_tags
        detail.item_vector = item_vector
        detail.image_url = _build_image_url(s3_key)

        await db.flush()
        logger.info("태깅 완료 (item_id=%d, tags=%s)", item_id, ai_tags)

    except Exception:
        logger.exception("process_tags 예외 (item_id=%d)", item_id)
        raise


async def get_item_tags(item_id: int, db: AsyncSession) -> TagsResponse:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalars().first()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={
            "success": False, "code": 404,
            "message": "아이템을 찾을 수 없습니다.", "data": None,
        })

    detail = await _get_detail(db, item)

    return TagsResponse(
        item_id=item_id,
        category=item.category,
        ai_tags=detail.ai_tags or [] if detail else [],
        has_vector=detail.item_vector is not None if detail else False,
        image_url=detail.image_url if detail else None,
    )