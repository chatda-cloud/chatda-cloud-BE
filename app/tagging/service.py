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

PENDING_CATEGORY = "분류중"


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
    if item.status == ItemStatus.LOST:
        result = await db.execute(select(LostItem).where(LostItem.item_id == item.id))
    else:
        result = await db.execute(select(FoundItem).where(FoundItem.item_id == item.id))
    return result.scalars().first()


async def process_tags(
    item_id: int,
    db: AsyncSession,
    image_bytes: bytes | None = None,
    image_pil: PILImage.Image | None = None,
    s3_key: str | None = None,
) -> dict:
    """
    태깅 파이프라인.
    item_name + raw_text + 이미지를 종합해 category, features, item_vector 추출.

    반환: {"category": str, "features": list, "image_url": str | None}
    """
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalars().first()
    if not item:
        logger.warning("process_tags: item %d not found", item_id)
        return {}

    detail = await _get_detail(db, item)
    if not detail:
        logger.warning("process_tags: detail not found for item %d", item_id)
        return {}

    loop = asyncio.get_running_loop()

    # ── 이미지 준비 ───────────────────────────────────────
    if image_bytes is None and s3_key:
        try:
            image_bytes, image_pil = await loop.run_in_executor(
                None, _download_s3_image, s3_key
            )
        except Exception:
            logger.exception("S3 다운로드 실패 (item_id=%d)", item_id)

    # ── 1. Rekognition → 힌트 라벨 ───────────────────────
    rek_labels: list[str] = []
    if s3_key:
        try:
            rek_labels = await loop.run_in_executor(
                None, rekognition.detect_labels, s3_key
            )
        except Exception:
            logger.exception("Rekognition 실패 (item_id=%d)", item_id)

    # ── 2. CLIP → item_vector ─────────────────────────────
    # item_name + raw_text 결합으로 텍스트 임베딩 품질 향상
    item_vector: list[float] | None = None
    try:
        if image_pil:
            item_vector = await loop.run_in_executor(
                None, clip.encode_image_from_pil, image_pil
            )
        else:
            text = f"{detail.item_name} {detail.raw_text or ''}".strip()
            if text:
                item_vector = await loop.run_in_executor(
                    None, clip.encode_text, text
                )
    except Exception:
        logger.exception("CLIP 인코딩 실패 (item_id=%d)", item_id)

    # ── 3. Gemini → category + features ──────────────────
    # item_name을 힌트로 제공해 category 정확도 향상
    gemini_result: dict | None = None
    user_hint = f"{detail.item_name}: {detail.raw_text or ''}".strip(": ")

    if image_bytes:
        try:
            gemini_result = await loop.run_in_executor(
                None,
                gemini.extract_from_image,
                image_bytes,
                rek_labels or None,
                user_hint,          # item_name + raw_text 함께 전달
            )
        except Exception:
            logger.exception("Gemini 이미지 분석 실패 (item_id=%d)", item_id)

    if gemini_result is None:
        try:
            gemini_result = await loop.run_in_executor(
                None, gemini.extract_from_text, user_hint
            )
        except Exception:
            logger.exception("Gemini 텍스트 분석 실패 (item_id=%d)", item_id)

    # ── 4. DB 저장 ────────────────────────────────────────
    features: list[str] = []
    category = item.category

    if gemini_result:
        features = gemini_result.get("color", []) + gemini_result.get("features", [])
        category = gemini_result.get("category") or item.category

    image_url = _build_image_url(s3_key) if s3_key else None

    item.category = category
    detail.features = features
    detail.item_vector = item_vector
    if image_url:
        detail.image_url = image_url

    await db.flush()
    logger.info(
        "태깅 완료 (item_id=%d, item_name=%s, category=%s, features=%s)",
        item_id, detail.item_name, category, features,
    )

    return {
        "category": category,
        "features": features,
        "image_url": image_url,
    }


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
        features=detail.features or [] if detail else [],
        has_vector=detail.item_vector is not None if detail else False,
        image_url=detail.image_url if detail else None,
    )