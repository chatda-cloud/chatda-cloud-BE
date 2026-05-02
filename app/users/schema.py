from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models import ItemStatus


class UserOut(BaseModel):
    id: int
    user_id: str
    email: str
    username: Optional[str]
    gender: Optional[str]
    birthdate: Optional[datetime]
    profile_image_url: Optional[str]
    phone: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateUsernameRequest(BaseModel):
    username: str


class UpdateProfileImageRequest(BaseModel):
    profile_image_url: str  # S3 object URL


# ── 아이템 요약 (목록 조회용) ──────────────────────────────
class LostItemSummary(BaseModel):
    item_id: int
    category: str
    status: ItemStatus
    location: str
    date_start: datetime
    date_end: datetime
    raw_text: Optional[str]
    image_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class FoundItemSummary(BaseModel):
    item_id: int
    category: str
    status: ItemStatus
    location: str
    found_date: datetime
    raw_text: Optional[str]
    image_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 매칭 요약 ──────────────────────────────────────────────
class MatchSummary(BaseModel):
    id: int
    lost_item_id: int
    found_item_id: int
    similarity_score: float
    is_confirmed: bool
    created_at: datetime

    model_config = {"from_attributes": True}