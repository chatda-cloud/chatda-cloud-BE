"""users 비즈니스 로직."""
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, Match, User


async def update_username(db: AsyncSession, user: User, username: str) -> User:
    user.username = username.strip()
    await db.commit()
    await db.refresh(user)
    return user


async def update_profile_image(db: AsyncSession, user: User, image_url: str) -> User:
    user.profile_image_url = image_url
    await db.commit()
    await db.refresh(user)
    return user


async def get_lost_items(db: AsyncSession, user_id: int) -> List[Item]:
    result = await db.execute(
        select(Item)
        .where(Item.owner_id == user_id, Item.item_type == "LOST")
        .order_by(Item.created_at.desc())
    )
    return result.scalars().all()


async def get_found_items(db: AsyncSession, user_id: int) -> List[Item]:
    result = await db.execute(
        select(Item)
        .where(Item.owner_id == user_id, Item.item_type == "FOUND")
        .order_by(Item.created_at.desc())
    )
    return result.scalars().all()


async def get_matches(db: AsyncSession, user_id: int) -> List[Match]:
    result = await db.execute(
        select(Match)
        .where(Match.user_id == user_id)
        .order_by(Match.created_at.desc())
    )
    return result.scalars().all()
