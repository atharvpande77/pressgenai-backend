from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer
from datetime import datetime
from uuid import UUID
from pydantic import computed_field, Field
from typing import Annotated

from src.models import NewsCategory
from src.news.utils import get_category_name
from src.schemas import CategorySerializerMixin
from src.aws.utils import get_images_with_urls

category_values = [category.value for category in NewsCategory]
class ArticleItem(CategorySerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    # snippet: str | None = None
    # full_text: str
    category: list[str] | None = []
    # tags: list[str] | None = None
    # images: list[dict] | None = Field(default=[], max_length=3)
    created_at: datetime
    updated_at: datetime | None = None
    publish_status: str
    published_at: datetime | None = None
    creator_username: str | None = None
    creator_first_name: str
    creator_last_name: str | None = None
    # creator_profile_image: str | None = None
    

class ArticleFullItem(CategorySerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    snippet: str | None = None
    full_text: str
    category: list[str] | None = []
    tags: list[str] | None = []
    slug: str | None = None
    images_keys: list[str] | None = Field(default=[], exclude=True)
    created_at: datetime
    published_at: datetime | None = None
    updated_at: datetime | None = None
    creator_username: str | None = None
    creator_first_name: str
    creator_last_name: str | None = None
    creator_profile_image: str | None = None
    can_edit: bool

    @computed_field
    @property
    def images(self) -> list[dict]:
        return get_images_with_urls(self.images_keys)

class EditArticleSchema(BaseModel):
    title: Annotated[str | None, Field(min_length=10, max_length=75)] = None
    snippet: Annotated[str | None, Field(min_length=100, max_length=2000)] = None
    full_text: Annotated[str | None, Field(min_length=500, max_length=50000)] = None
    category: list[str] | None = None
    tags: list[str] | None = None
    images_keys: list[str] | None = Field(default=None, max_length=3)

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v is None:
            return v

        category_values = [category.value for category in NewsCategory]
        
        # Check if the lowercase version matches any category (case-insensitive)
        
        if not all(cat.lower() in category_values for cat in v):
            raise ValueError(
                f"Category must be one of: {', '.join(category_values)}"
            )
        
        # Return the properly cased version from the enum
        return [category.value for category in NewsCategory if category.value.lower() in v]
    

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