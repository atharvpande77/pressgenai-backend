from pydantic import BaseModel, ConfigDict, Field, AliasPath, field_validator, computed_field, PlainSerializer
from typing import Annotated
from uuid import UUID

from datetime import datetime, timedelta, timezone

from src.schemas import GeneratedStoryResponseSchema, CategoriesDB, make_profile_image_mixin, make_images_mixin
from src.editor.schemas import CreatorOrEditor


ImagesMixin = make_images_mixin("images_keys")
ProfileImageMixin = make_profile_image_mixin("profile_image_key")

IST = timezone(timedelta(hours=5, minutes=30))


def _to_ist_iso(value: datetime | None) -> str | None:
    """Timestamps are stored as naive IST wall-clock times (see time_diff_interval in
    src/models.py); publish them with an explicit +05:30 offset."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(IST).isoformat()


ISTDateTime = Annotated[datetime, PlainSerializer(_to_ist_iso, return_type=str | None, when_used="json")]


class PrimaryCategoryMixin:
    """`categories` are ordered (article_categories.position); the first is primary and
    determines the article's canonical URL /{category}/{slug}."""

    @computed_field
    @property
    def primary_category(self) -> CategoriesDB | None:
        categories = getattr(self, "categories", None) or []
        return categories[0] if categories else None

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


class ArticleListResponse(PrimaryCategoryMixin, ImagesMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    snippet: str | None = None
    # submitted_at: datetime | None = None
    # publish_status: str | None = None
    published_at: ISTDateTime | None = None
    updated_at: ISTDateTime | None = None
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


class ArticleDetailResponse(PrimaryCategoryMixin, GeneratedStoryResponseSchema):
    model_config = ConfigDict(from_attributes=True)

    published_at: ISTDateTime | None = None
    created_at: ISTDateTime | None = None
    updated_at: ISTDateTime | None = None
    city_id: UUID | None = None
    city: str | None = Field(default=None, validation_alias=AliasPath("city", "name"))
    creator: ArticlePerson = Field(validation_alias=AliasPath("author", "user"))
    editor: ArticlePerson | dict = Field(default_factory=dict)

    @field_validator("editor", mode="before")
    @classmethod
    def normalize_editor(cls, v):
        return {} if v is None else v


class CreatorArticleListResponse(PrimaryCategoryMixin, ImagesMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    snippet: str | None = None
    published_at: ISTDateTime | None = None
    updated_at: ISTDateTime | None = None
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
    total_count: int | None = None
    articles: list[CreatorArticleListResponse] = []


class SitemapArticleResponse(PrimaryCategoryMixin, BaseModel):
    """Minimal article row for sitemaps."""
    model_config = ConfigDict(from_attributes=True)

    slug: str
    published_at: ISTDateTime | None = None
    updated_at: ISTDateTime | None = None
    categories: list[CategoriesDB] = Field(default_factory=list, exclude=True)


class SitemapAuthorResponse(BaseModel):
    username: str
    lastmod: ISTDateTime | None = None
