from pydantic import BaseModel


class TaggingResponse(BaseModel):
    item_id: int
    category: str
    ai_tags: list[str]
    item_vector_stored: bool