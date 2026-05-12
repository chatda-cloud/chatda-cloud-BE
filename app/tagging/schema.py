from pydantic import BaseModel, Field


class ProcessTagsRequest(BaseModel):
    s3_key: str = Field(..., alias="s3Key")

    model_config = {"populate_by_name": True}


class TagsResponse(BaseModel):
    item_id: int = Field(..., alias="itemId")
    category: str | None = None
    features: list[str] = Field(..., alias="features")
    has_vector: bool = Field(..., alias="hasVector")
    image_url: str | None = Field(None, alias="imageUrl")

    model_config = {"populate_by_name": True}
