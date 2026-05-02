from datetime import datetime
from typing import Optional

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
    item_name: str                  # 물건 이름 (예: 에어팟, 지갑)
    date_start: datetime            # 분실 시작 추정 일시
    date_end: datetime              # 분실 종료 추정 일시
    location: str                   # 분실 장소
    raw_text: Optional[str] = None  # 상세 설명 (선택)


class LostItemUpdate(BaseModel):
    item_name: Optional[str] = None
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    location: Optional[str] = None
    raw_text: Optional[str] = None


class LostItemResponse(BaseModel):
    item_id: int
    item_name: str
    date_start: datetime
    date_end: datetime
    location: str
    raw_text: Optional[str]
    image_url: Optional[str]
    features: Optional[list]
    item: ItemResponse

    model_config = {"from_attributes": True}


# ── 습득물 ─────────────────────────────────────────────────
class FoundItemCreate(BaseModel):
    item_name: str                  # 물건 이름 (예: 에어팟, 지갑)
    found_date: datetime            # 습득 일시
    location: str                   # 습득 장소
    raw_text: Optional[str] = None  # 상세 설명 (선택)


class FoundItemUpdate(BaseModel):
    item_name: Optional[str] = None
    found_date: Optional[datetime] = None
    location: Optional[str] = None
    raw_text: Optional[str] = None


class FoundItemResponse(BaseModel):
    item_id: int
    item_name: str
    found_date: datetime
    location: str
    raw_text: Optional[str]
    image_url: Optional[str]
    features: Optional[list]
    item: ItemResponse

    model_config = {"from_attributes": True}


# ── 등록 최종 응답 (태깅 + 매칭 결과 포함) ────────────────
class ItemRegisterResponse(BaseModel):
    item_id: int
    item_name: str
    category: str
    features: Optional[list]
    image_url: Optional[str]
    matched_count: int