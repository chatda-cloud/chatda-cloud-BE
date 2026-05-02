"""items 비즈니스 로직 - 등록 시 태깅 자동 실행. 매칭은 router에서 BackgroundTasks로 처리."""
import io
import logging

from fastapi import HTTPException
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.items.schema import (
    FoundItemCreate,
    FoundItemResponse,
    FoundItemUpdate,
    ItemRegisterResponse,
    ItemResponse,
    LostItemCreate,
    LostItemResponse,
    LostItemUpdate,
)
from app.models import FoundItem, Item, ItemStatus, LostItem
from app.tagging.service import PENDING_CATEGORY, process_tags

logger = logging.getLogger(__name__)


# ── 응답 변환 헬퍼 ─────────────────────────────────────────
def lost_item_to_response(lost_item: LostItem) -> LostItemResponse:
    return LostItemResponse(
        item_id=lost_item.item_id,
        item_name=lost_item.item_name,
        date_start=lost_item.date_start,
        date_end=lost_item.date_end,
        location=lost_item.location,
        raw_text=lost_item.raw_text,
        image_url=lost_item.image_url,
        features=lost_item.features,
        item=ItemResponse.model_validate(lost_item.item),
    )


def found_item_to_response(found_item: FoundItem) -> FoundItemResponse:
    return FoundItemResponse(
        item_id=found_item.item_id,
        item_name=found_item.item_name,
        found_date=found_item.found_date,
        location=found_item.location,
        raw_text=found_item.raw_text,
        image_url=found_item.image_url,
        features=found_item.features,
        item=ItemResponse.model_validate(found_item.item),
    )


# ── 조회 헬퍼 (없으면 404) ─────────────────────────────────
async def get_lost_item_or_404(db: AsyncSession, item_id: int) -> LostItem:
    result = await db.execute(
        select(LostItem)
        .options(joinedload(LostItem.item))
        .where(LostItem.item_id == item_id)
    )
    lost_item = result.scalars().first()
    if lost_item is None:
        raise HTTPException(status_code=404, detail={
            "success": False, "code": 404, "message": "분실물을 찾을 수 없습니다.", "data": None,
        })
    return lost_item


async def get_found_item_or_404(db: AsyncSession, item_id: int) -> FoundItem:
    result = await db.execute(
        select(FoundItem)
        .options(joinedload(FoundItem.item))
        .where(FoundItem.item_id == item_id)
    )
    found_item = result.scalars().first()
    if found_item is None:
        raise HTTPException(status_code=404, detail={
            "success": False, "code": 404, "message": "습득물을 찾을 수 없습니다.", "data": None,
        })
    return found_item


# ── 소유자 검증 ───────────────────────────────────────────
def check_owner(item_user_id: int, current_user_id: int) -> None:
    if item_user_id != current_user_id:
        raise HTTPException(status_code=403, detail={
            "success": False, "code": 403, "message": "권한이 없습니다.", "data": None,
        })


# ── 분실물 등록 (태깅만 수행, 매칭은 router에서 BackgroundTasks로) ──
async def create_lost_item(
    db: AsyncSession,
    user_id: int,
    body: LostItemCreate,
    image_bytes: bytes | None = None,
) -> ItemRegisterResponse:
    # 1. Item 생성
    item = Item(user_id=user_id, category=PENDING_CATEGORY, status=ItemStatus.LOST)
    db.add(item)
    await db.flush()

    # 2. LostItem 생성
    lost_item = LostItem(
        item_id=item.id,
        item_name=body.item_name,
        date_start=body.date_start,
        date_end=body.date_end,
        location=body.location,
        raw_text=body.raw_text,
    )
    db.add(lost_item)
    await db.flush()

    # 3. 이미지 PIL 변환
    image_pil: PILImage.Image | None = None
    if image_bytes:
        try:
            image_pil = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            logger.warning("이미지 변환 실패 (item_id=%d)", item.id)

    # 4. 태깅 (category, features, item_vector 자동 추출)
    tag_result = await process_tags(
        item_id=item.id,
        db=db,
        image_bytes=image_bytes,
        image_pil=image_pil,
    )

    return ItemRegisterResponse(
        item_id=item.id,
        item_name=body.item_name,
        category=tag_result.get("category", PENDING_CATEGORY),
        features=tag_result.get("features", []),
        image_url=tag_result.get("image_url"),
        matched_count=0,  # 매칭은 백그라운드에서 처리
    )


# ── 습득물 등록 (태깅만 수행, 매칭은 router에서 BackgroundTasks로) ──
async def create_found_item(
    db: AsyncSession,
    user_id: int,
    body: FoundItemCreate,
    image_bytes: bytes | None = None,
) -> ItemRegisterResponse:
    # 1. Item 생성
    item = Item(user_id=user_id, category=PENDING_CATEGORY, status=ItemStatus.FOUND)
    db.add(item)
    await db.flush()

    # 2. FoundItem 생성
    found_item = FoundItem(
        item_id=item.id,
        item_name=body.item_name,
        found_date=body.found_date,
        location=body.location,
        raw_text=body.raw_text,
    )
    db.add(found_item)
    await db.flush()

    # 3. 이미지 PIL 변환
    image_pil: PILImage.Image | None = None
    if image_bytes:
        try:
            image_pil = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            logger.warning("이미지 변환 실패 (item_id=%d)", item.id)

    # 4. 태깅
    tag_result = await process_tags(
        item_id=item.id,
        db=db,
        image_bytes=image_bytes,
        image_pil=image_pil,
    )

    return ItemRegisterResponse(
        item_id=item.id,
        item_name=body.item_name,
        category=tag_result.get("category", PENDING_CATEGORY),
        features=tag_result.get("features", []),
        image_url=tag_result.get("image_url"),
        matched_count=0,
    )


# ── 조회 ───────────────────────────────────────────────────
async def read_lost_item(db: AsyncSession, item_id: int) -> LostItemResponse:
    return lost_item_to_response(await get_lost_item_or_404(db, item_id))


async def read_found_item(db: AsyncSession, item_id: int) -> FoundItemResponse:
    return found_item_to_response(await get_found_item_or_404(db, item_id))


# ── 수정 ───────────────────────────────────────────────────
async def update_lost_item(
    db: AsyncSession, item_id: int, user_id: int, body: LostItemUpdate
) -> LostItemResponse:
    lost_item = await get_lost_item_or_404(db, item_id)
    check_owner(lost_item.item.user_id, user_id)

    if body.item_name is not None: lost_item.item_name = body.item_name
    if body.date_start is not None: lost_item.date_start = body.date_start
    if body.date_end is not None: lost_item.date_end = body.date_end
    if body.location is not None: lost_item.location = body.location
    if body.raw_text is not None: lost_item.raw_text = body.raw_text

    await db.flush()
    await db.refresh(lost_item, ["item"])
    return lost_item_to_response(lost_item)


async def update_found_item(
    db: AsyncSession, item_id: int, user_id: int, body: FoundItemUpdate
) -> FoundItemResponse:
    found_item = await get_found_item_or_404(db, item_id)
    check_owner(found_item.item.user_id, user_id)

    if body.item_name is not None: found_item.item_name = body.item_name
    if body.found_date is not None: found_item.found_date = body.found_date
    if body.location is not None: found_item.location = body.location
    if body.raw_text is not None: found_item.raw_text = body.raw_text

    await db.flush()
    await db.refresh(found_item, ["item"])
    return found_item_to_response(found_item)


# ── 삭제 ───────────────────────────────────────────────────
async def delete_lost_item(db: AsyncSession, item_id: int, user_id: int) -> None:
    lost_item = await get_lost_item_or_404(db, item_id)
    check_owner(lost_item.item.user_id, user_id)
    await db.delete(lost_item.item)
    await db.flush()


async def delete_found_item(db: AsyncSession, item_id: int, user_id: int) -> None:
    found_item = await get_found_item_or_404(db, item_id)
    check_owner(found_item.item.user_id, user_id)
    await db.delete(found_item.item)
    await db.flush()