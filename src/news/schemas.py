from pydantic import BaseModel, ConfigDict
from uuid import UUID

from src.schemas import GeneratedStoryResponseSchema


class ArticleResponse(GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)
    
    creator_id: UUID | None = None
    creator_first_name: str | None = None
    creator_last_name: str | None = None
    editor_id: UUID | None = None
    editor_first_name: str | None = None
    editor_last_name: str | None = None

class CreatorProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str | None = None
    bio: str | None = None
    articles: list[ArticleResponse] | None = []