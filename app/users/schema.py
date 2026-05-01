from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    gender: Optional[str]
    birthDate: Optional[date]
    profileImage: Optional[str]
    createdAt: datetime

    model_config = {"from_attributes": True}


class UpdateUsernameRequest(BaseModel):
    username: str


class UpdateProfileImageRequest(BaseModel):
    profileImage: str   # S3 object URL


# ── 아이템 / 매칭 요약 (목록 조회용) ─────────────────────────────────────────

class ItemSummary(BaseModel):
    id: int
    itemType: str
    category: Optional[str]
    rawText: Optional[str]
    imageUrl: Optional[str]
    status: str
    createdAt: datetime

    model_config = {"from_attributes": True}


class MatchSummary(BaseModel):
    id: int
    lostItemId: int
    foundItemId: int
    similarity: int
    status: str
    createdAt: datetime

    model_config = {"from_attributes": True}
