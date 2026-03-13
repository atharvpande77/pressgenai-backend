from pydantic import BaseModel, ConfigDict, Field, AliasPath, field_validator
from uuid import UUID

from datetime import datetime

from src.schemas import GeneratedStoryResponseSchema, CategoriesDB, make_profile_image_mixin, make_images_mixin
from src.editor.schemas import CreatorOrEditor


ImagesMixin = make_images_mixin("images_keys")
ProfileImageMixin = make_profile_image_mixin("profile_image_key")

class ArticleResponse(GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    snippet: str
    published_at: datetime
    Categories: list[CategoriesDB]
    city_id: UUID
    city: str
    creator: CreatorOrEditor
    editor: CreatorOrEditor
    

class EditorItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str | None = None
    first_name: str
    last_name: str | None = None

class ArticleItem(GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)

    editor_first_name: str | None = None
    editor_last_name: str | None = None
    editor_username: str | None = None
    editor_profile_image: str | None = None


class ArticlePerson(ProfileImageMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class ArticleListResponse(ImagesMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    snippet: str | None = None
    # submitted_at: datetime | None = None
    # publish_status: str | None = None
    published_at: datetime | None = None
    slug: str | None = None
    creator: ArticlePerson = Field(validation_alias=AliasPath("author", "user"))
    editor: ArticlePerson | dict = Field(default_factory=dict)
    # can_edit: bool | None = None
    city_id: UUID | None = None
    city: str | None = Field(default=None, validation_alias=AliasPath("city", "name"))
    categories: list[CategoriesDB] = []

    @field_validator("editor", mode="before")
    @classmethod
    def normalize_editor(cls, v):
        return {} if v is None else v


class ArticleDetailResponse(GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)

    published_at: datetime | None = None
    city_id: UUID | None = None
    city: str | None = Field(default=None, validation_alias=AliasPath("city", "name"))
    creator: ArticlePerson = Field(validation_alias=AliasPath("author", "user"))
    editor: ArticlePerson | dict = Field(default_factory=dict)

    @field_validator("editor", mode="before")
    @classmethod
    def normalize_editor(cls, v):
        return {} if v is None else v


class CreatorArticleListResponse(ImagesMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    slug: str | None = None
    editor: ArticlePerson | dict = Field(default_factory=dict)
    city_id: UUID | None = None
    city: str | None = Field(default=None, validation_alias=AliasPath("city", "name"))
    categories: list[CategoriesDB] = []

    @field_validator("editor", mode="before")
    @classmethod
    def normalize_editor(cls, v):
        return {} if v is None else v


class CreatorProfileResponse(ProfileImageMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    creator_username: str | None = None
    first_name: str
    last_name: str | None = None
    username: str | None = None
    bio: str | None = None
    articles: list[CreatorArticleListResponse] = []
