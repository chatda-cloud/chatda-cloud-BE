"""users 비즈니스 로직."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import FoundItem, Item, ItemStatus, LostItem, Match, User


async def update_username(db: AsyncSession, user: User, username: str) -> User:
    user.username = username.strip()
    await db.flush()
    await db.refresh(user)
    return user


async def update_profile_image(db: AsyncSession, user: User, image_url: str) -> User:
    user.profile_image_url = image_url
    await db.flush()
    await db.refresh(user)
    return user


async def get_my_lost_items(db: AsyncSession, user_id: int) -> list[LostItem]:
    result = await db.execute(
        select(LostItem)
        .join(Item, Item.id == LostItem.item_id)
        .options(joinedload(LostItem.item))
        .where(Item.user_id == user_id, Item.status == ItemStatus.LOST)
        .order_by(Item.created_at.desc())
    )
    return result.scalars().all()


async def get_my_found_items(db: AsyncSession, user_id: int) -> list[FoundItem]:
    result = await db.execute(
        select(FoundItem)
        .join(Item, Item.id == FoundItem.item_id)
        .options(joinedload(FoundItem.item))
        .where(Item.user_id == user_id, Item.status == ItemStatus.FOUND)
        .order_by(Item.created_at.desc())
    )
    return result.scalars().all()


async def get_my_matches(db: AsyncSession, user_id: int) -> list[Match]:
    """유저가 등록한 분실물 또는 습득물과 연결된 매칭 목록 조회."""
    result = await db.execute(
        select(Match)
        .join(Item, (Item.id == Match.lost_item_id) | (Item.id == Match.found_item_id))
        .where(Item.user_id == user_id)
        .order_by(Match.created_at.desc())
        .distinct()
    )
    return result.scalars().all()