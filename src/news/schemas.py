from pydantic import BaseModel, ConfigDict
from uuid import UUID

from src.schemas import GeneratedStoryResponseSchema


class ArticleResponse(GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)
    
    creator_username: str | None = None
    creator_first_name: str | None = None
    creator_last_name: str | None = None
    editor_first_name: str | None = None
    editor_last_name: str | None = None

class EditorItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str | None = None
    first_name: str
    last_name: str | None = None

class ArticleItem(GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)

    editor: EditorItem


class CreatorProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: str
    last_name: str | None = None
    username: str | None = None
    bio: str | None = None
    articles: list[ArticleItem] = []