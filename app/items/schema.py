from datetime import datetime

from pydantic import BaseModel

from app.models import ItemStatus


# ── 공통 ───────────────────────────────────────────────────
class ItemResponse(BaseModel):
    id: int
    user_id: int
    category: str
    status: ItemStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 분실물 ─────────────────────────────────────────────────
class LostItemCreate(BaseModel):
    category: str
    date_start: datetime
    date_end: datetime
    location: str
    raw_text: str | None = None


class LostItemUpdate(BaseModel):
    category: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    location: str | None = None
    raw_text: str | None = None


class LostItemResponse(BaseModel):
    item_id: int
    date_start: datetime
    date_end: datetime
    location: str
    raw_text: str | None
    image_url: str | None
    ai_tags: list | None
    item: ItemResponse

    model_config = {"from_attributes": True}


# ── 습득물 ─────────────────────────────────────────────────
class FoundItemCreate(BaseModel):
    category: str
    found_date: datetime
    location: str
    raw_text: str | None = None


class FoundItemUpdate(BaseModel):
    category: str | None = None
    found_date: datetime | None = None
    location: str | None = None
    raw_text: str | None = None


class FoundItemResponse(BaseModel):
    item_id: int
    found_date: datetime
    location: str
    raw_text: str | None
    image_url: str | None
    ai_tags: list | None
    item: ItemResponse

    model_config = {"from_attributes": True}