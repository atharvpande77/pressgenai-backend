from pydantic import BaseModel, ConfigDict, Field, field_validator, EmailStr
from datetime import datetime
from uuid import UUID
from pydantic import computed_field
from typing import Annotated

from src.models import (
    NewsCategory,
    LocationScope
)
from src.news.utils import get_category_name
from src.schemas import (
    ContentSizeLimits,
    CategoriesDB,
    GeneratedStoryResponseSchema,
    make_images_mixin,
    make_profile_image_mixin
)
from src.aws.utils import get_images_with_urls

category_values = [category.value for category in NewsCategory]
    
class CreatorOrEditor(make_profile_image_mixin('profile_image_key'), BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    first_name: str
    last_name: str  | None = None
    username: str | None = None
    # profile_image: str | None = None


class SimpleCategory(BaseModel):
    id: UUID
    name: str
    value: str


class SimpleCity(BaseModel):
    id: UUID
    name: str


class EditorProfile(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None = None
    email: EmailStr
    username: str | None = None
    profile_image: str | None = None
    categories: list[SimpleCategory] = Field(default_factory=list)
    cities: list[SimpleCity] = Field(default_factory=list)


class EditorChangePassword(BaseModel):
    old_password: str
    new_password: str

class ArticleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    submitted_at: datetime | None = None
    publish_status: str
    published_at: datetime | None = None
    creator: CreatorOrEditor
    editor: CreatorOrEditor | dict = {}
    can_edit: bool | None = None
    city_id: UUID | None = None
    city: str | None = None
    categories: list[CategoriesDB] | None = None

class ArticleFullResponse(GeneratedStoryResponseSchema, ArticleItem):
    model_config = ConfigDict(from_attributes=True)

    location_scope: str | None = None


class EditArticleSchema(BaseModel):
    title: Annotated[str | None, Field(min_length=ContentSizeLimits.TITLE_MIN, max_length=ContentSizeLimits.TITLE_MAX)] = None
    snippet: Annotated[str | None, Field(min_length=ContentSizeLimits.SNIPPET_MIN, max_length=ContentSizeLimits.SNIPPET_MAX)] = None
    full_text: Annotated[str | None, Field(min_length=ContentSizeLimits.FULL_TEXT_MIN, max_length=ContentSizeLimits.FULL_TEXT_MAX)] = None
    categories: list[UUID] | None = Field(default_factory=list, min_length=ContentSizeLimits.CATEGORY_MIN, max_length=ContentSizeLimits.CATEGORY_MAX)
    location_scope: LocationScope | None = None
    city_id: UUID | None = None
    tags: list[str] | None = Field(default_factory=list, max_length=ContentSizeLimits.TAGS_MAX)
    images_keys: list[str] | None = Field(default_factory=list, max_length=3)
    

class RejectArticleSchema(BaseModel):
    reason: Annotated[str, Field(min_length=20, max_length=1200)]


class RejectedEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rejection_reason: str
    publish_status: str
    
    
class UpdateCreatorPassword(BaseModel):
    editor_password: str
    new_password: str
    
class CreatorItem(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    bio: str | None = None
    username: str | None = None
    creator_profile_image: str | None = None
    published_count: int | None = None
    active: bool | None = None
    
    
class CreateCreatorSchema(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    active: bool = True
