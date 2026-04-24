from datetime import datetime

from pydantic import BaseModel


class MatchResponse(BaseModel):
    id: int
    lost_item_id: int
    found_item_id: int
    similarity_score: float
    is_confirmed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    total: int
    matches: list[MatchResponse]


class MatchConfirmRequest(BaseModel):
    is_confirmed: bool