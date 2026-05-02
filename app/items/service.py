"""items 비즈니스 로직 (DB 조작, 권한, 응답 매핑)."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.items.schema import (
    FoundItemCreate,
    FoundItemResponse,
    FoundItemUpdate,
    ItemResponse,
    LostItemCreate,
    LostItemResponse,
    LostItemUpdate,
)
from app.models import FoundItem, Item, ItemStatus, LostItem


# ── 응답 변환 헬퍼 ─────────────────────────────────────────
def lost_item_to_response(lost_item: LostItem) -> LostItemResponse:
    return LostItemResponse(
        item_id=lost_item.item_id,
        date_start=lost_item.date_start,
        date_end=lost_item.date_end,
        location=lost_item.location,
        raw_text=lost_item.raw_text,
        image_url=lost_item.image_url,
        ai_tags=lost_item.ai_tags,
        item=ItemResponse.model_validate(lost_item.item),
    )


def found_item_to_response(found_item: FoundItem) -> FoundItemResponse:
    return FoundItemResponse(
        item_id=found_item.item_id,
        found_date=found_item.found_date,
        location=found_item.location,
        raw_text=found_item.raw_text,
        image_url=found_item.image_url,
        ai_tags=found_item.ai_tags,
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
        raise HTTPException(
            status_code=404,
            detail={"success": False, "code": 404, "message": "분실물을 찾을 수 없습니다.", "data": None},
        )
    return lost_item


async def get_found_item_or_404(db: AsyncSession, item_id: int) -> FoundItem:
    result = await db.execute(
        select(FoundItem)
        .options(joinedload(FoundItem.item))
        .where(FoundItem.item_id == item_id)
    )
    found_item = result.scalars().first()
    if found_item is None:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "code": 404, "message": "습득물을 찾을 수 없습니다.", "data": None},
        )
    return found_item


# ── 소유자 검증 헬퍼 ───────────────────────────────────────
def check_owner(item_user_id: int, current_user_id: int) -> None:
    if item_user_id != current_user_id:
        raise HTTPException(
            status_code=403,
            detail={"success": False, "code": 403, "message": "권한이 없습니다.", "data": None},
        )


# ── CRUD ───────────────────────────────────────────────────
async def create_lost_item(db: AsyncSession, user_id: int, body: LostItemCreate) -> LostItemResponse:
    item = Item(user_id=user_id, category=body.category, status=ItemStatus.LOST)
    db.add(item)
    await db.flush()  # item.id 확보 (commit은 get_db()가 처리)

    lost_item = LostItem(
        item_id=item.id,
        date_start=body.date_start,
        date_end=body.date_end,
        location=body.location,
        raw_text=body.raw_text,
    )
    db.add(lost_item)
    await db.flush()

    await db.refresh(lost_item, ["item"])
    return lost_item_to_response(lost_item)


async def create_found_item(db: AsyncSession, user_id: int, body: FoundItemCreate) -> FoundItemResponse:
    item = Item(user_id=user_id, category=body.category, status=ItemStatus.FOUND)
    db.add(item)
    await db.flush()

    found_item = FoundItem(
        item_id=item.id,
        found_date=body.found_date,
        location=body.location,
        raw_text=body.raw_text,
    )
    db.add(found_item)
    await db.flush()

    await db.refresh(found_item, ["item"])
    return found_item_to_response(found_item)


async def read_lost_item(db: AsyncSession, item_id: int) -> LostItemResponse:
    lost_item = await get_lost_item_or_404(db, item_id)
    return lost_item_to_response(lost_item)


async def read_found_item(db: AsyncSession, item_id: int) -> FoundItemResponse:
    found_item = await get_found_item_or_404(db, item_id)
    return found_item_to_response(found_item)


async def update_lost_item(
    db: AsyncSession, item_id: int, user_id: int, body: LostItemUpdate
) -> LostItemResponse:
    lost_item = await get_lost_item_or_404(db, item_id)
    check_owner(lost_item.item.user_id, user_id)

    if body.category is not None:
        lost_item.item.category = body.category
    if body.date_start is not None:
        lost_item.date_start = body.date_start
    if body.date_end is not None:
        lost_item.date_end = body.date_end
    if body.location is not None:
        lost_item.location = body.location
    if body.raw_text is not None:
        lost_item.raw_text = body.raw_text

    await db.flush()
    await db.refresh(lost_item, ["item"])
    return lost_item_to_response(lost_item)


async def delete_lost_item(db: AsyncSession, item_id: int, user_id: int) -> None:
    lost_item = await get_lost_item_or_404(db, item_id)
    check_owner(lost_item.item.user_id, user_id)
    # items 삭제 시 CASCADE로 lost_items도 같이 삭제됨
    await db.delete(lost_item.item)
    await db.flush()


async def update_found_item(
    db: AsyncSession, item_id: int, user_id: int, body: FoundItemUpdate
) -> FoundItemResponse:
    found_item = await get_found_item_or_404(db, item_id)
    check_owner(found_item.item.user_id, user_id)

    if body.category is not None:
        found_item.item.category = body.category
    if body.found_date is not None:
        found_item.found_date = body.found_date
    if body.location is not None:
        found_item.location = body.location
    if body.raw_text is not None:
        found_item.raw_text = body.raw_text

    await db.flush()
    await db.refresh(found_item, ["item"])
    return found_item_to_response(found_item)


async def delete_found_item(db: AsyncSession, item_id: int, user_id: int) -> None:
    found_item = await get_found_item_or_404(db, item_id)
    check_owner(found_item.item.user_id, user_id)
    await db.delete(found_item.item)
    await db.flush()