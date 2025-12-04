from pydantic import BaseModel, field_validator, model_validator, ConfigDict, Field, HttpUrl, ConfigDict, field_serializer, computed_field
from typing import Literal, Optional, Annotated
from uuid import UUID
from datetime import datetime
from enum import Enum

from src.news.utils import get_category_name
from src.models import NewsCategory

class Location(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None
    
    @field_validator('city', 'state', 'country')
    @classmethod
    def capitalize_fields(cls, v):
        return v.upper() if v is not None else v

class LocationDataSchema(BaseModel):
    scope: Literal['CITY', 'STATE', 'COUNTRY', 'INTERNATIONAL']
    query: str
    country_code: Optional[str] = None
    location: Location | None = None
    
    @field_validator('query')
    @classmethod
    def capitalize_query(cls, v):
        return v.upper() if v is not None else v
    
    @model_validator(mode='after')
    def validate_location_scope(self):
        if self.scope == 'INTERNATIONAL':
            # For international scope, location can be None (no validation needed)
            pass
        else:
            # For non-international scope, location must be provided
            if self.location is None:
                raise ValueError(f"Location is required when scope is '{self.scope}'")
        
        return self

class StoriesModel(BaseModel):
    """Individual story response model"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(..., description="Unique identifier for the story")
    title: str = Field(..., description="Story headline/title")
    snippet: str = Field(..., description="Brief description or excerpt of the story")
    link: HttpUrl = Field(..., description="URL to the full story")
    source: str = Field(..., max_length=100, description="Name of the news source")
    published_timestamp: datetime = Field(..., description="When the story was published")
    thumbnail: Optional[HttpUrl] = Field(None, max_length=300, description="URL to story thumbnail image")
    # location_id: UUID = Field(..., description="ID of the associated location")

class StoriesResponseModel(BaseModel):
    count: int
    stories: list[StoriesModel]

class GenerateOptionsSchema(BaseModel):
    tone: Literal['neutral', 'formal', 'casual', 'professional']
    style: Literal['informative', 'narrative', 'breaking news', 'opinion']
    # length: Annotated[int, Field(strict=True, ge=100, le=400)]
    word_length: Literal['short', 'medium', 'long']
    language: str

class ReqSchema(BaseModel):
    sys_prompt: str
    format: Literal['News', 'Story', 'Opinion', 'Feature', 'Editorial']
    what: Optional[str] = None
    where: Optional[str] = None
    who: Optional[str] = None
    when: Optional[str] = None
    why: Optional[str] = None
    how: Optional[str] = None

class CreationMode(str, Enum):
    MANUAL = "manual"
    AI = "ai"

class ContentSizeLimits:
    TITLE_MIN: int = 5
    TITLE_MAX: int = 120
    
    SNIPPET_MIN: int = 50
    SNIPPET_MAX: int = 2500
    
    FULL_TEXT_MIN: int = 250
    FULL_TEXT_MAX: int = 75000
    
    CONTEXT_MIN: int = 50
    CONTEXT_MAX: int = 1200
    
    TAGS_MIN: int = 1
    TAGS_MAX: int = 15
    
    CATEGORY_MIN: int = 1
    CATEGORY_MAX: int = 3
    
    ANSWER_MIN: int = 8
    ANSWER_MAX: int = 2000


class CreateManualStorySchema(BaseModel):
    title: str | None = Field(None, min_length=ContentSizeLimits.TITLE_MIN, max_length=ContentSizeLimits.TITLE_MAX)
    # english_title: str = Field(..., min_length=10, max_length=120)
    # context: str = Field(..., min_length=50, max_length=1200)
    full_text: str = Field(..., min_length=ContentSizeLimits.FULL_TEXT_MIN, max_length=ContentSizeLimits.FULL_TEXT_MAX)
    # snippet: str = Field(..., min_length=50, max_length=400)
    # category: list[str] = Field(..., min_length=1, max_length=3)
    # tags: list[str] = Field(..., min_length=1, max_length=15)
    images_keys: list[str] = Field(default_factory=list)
    language: str | None = Field(default="Marathi")
    
    # @field_validator('category')
    # @classmethod
    # def validate_categories(cls, v):
    #     valid_categories = [cat.value for cat in NewsCategory]
    #     for cat in v:
    #         if cat not in valid_categories:
    #             raise ValueError(f'Invalid category: {cat}. Must be one of: {", ".join(valid_categories)}')
    #     return v


class CreateStorySchema(BaseModel):
    # title: Annotated[str, Field(max_length=75)] = ""
    context: str | None = Field(None, min_length=ContentSizeLimits.CONTEXT_MIN, max_length=ContentSizeLimits.CONTEXT_MAX)
    options: GenerateOptionsSchema | None = None
    mode: CreationMode = Field(default=CreationMode.AI)
    manual_story: Optional[CreateManualStorySchema] = None
    
    @model_validator(mode='after')
    def validate_mode_requirements(self):
        if self.mode == CreationMode.AI:
            if not self.context:
                raise ValueError('context is required when mode is ai_assisted')
            if not self.options:
                raise ValueError('options is required when mode is ai_assisted')
        if self.mode == CreationMode.MANUAL and not self.manual_story:
            raise ValueError('manual_story is required when mode is manual')
        return self
class GenerateStorySchema(BaseModel):
    what: str = Field(..., min_length=10, max_length=200)
    where: str = Field(..., min_length=10, max_length=200)
    who: str = Field(..., min_length=10, max_length=200)
    when: str = Field(..., min_length=10, max_length=200)
    why: str = Field(..., min_length=10, max_length=200)
    how: str = Field(..., min_length=10, max_length=200)
    options: GenerateOptionsSchema


class QuestionsResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_key: str
    # question_type: Literal["what", "who", "where", "why", "when", "how", "sources"]
    question_text: str

class AnswerSchema(BaseModel):
    question_id: str
    answer_text: str = Field(..., min_length=ContentSizeLimits.ANSWER_MIN, max_length=ContentSizeLimits.ANSWER_MAX)

class ArticleImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str | None = None
    url: str | None = None

def serialize_categories(categories: list[str] | None) -> list[str]:
    """Convert category keys to localized names"""
    if not categories:
        return []
    
    return [{"category_value": cat, "category_name": get_category_name(cat)} for cat in categories]
class CategorySerializerMixin:
    """Mixin for category serialization"""
    
    @field_serializer('category')
    def serialize_category(self, categories: list[str] | None) -> list[dict[str, str]]:
        return serialize_categories(categories)

# class ImageSerializerMixin:
#     """Mixin for image serialization"""
    
#     @field_serializer('images_keys')
#     def serialize_images_keys(self, images_keys: list[str] | None) -> list[dict[str, str]]:
#         return [{"key": key, "url": get_full_s3_object_url(key)} for key in images_keys]
    
class GeneratedStoryResponseSchema(CategorySerializerMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    slug: str | None = None
    snippet: str | None = None
    full_text: str | None = None
    category: list[str] | None = []
    tags: list[str] | None = []
    images: list | None = Field(default=[])
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    
class CreateStoryResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    publish_status: str
    mode: str
    # AI mode fields
    context: str | None = None
    tone: str | None = None
    style: str | None = None
    language: str | None = None
    word_length: str | None = None

    # Manual mode fields
    manual_story: GeneratedStoryResponseSchema | None = None


# class UserStoryResponseSchema(CreateStorySchema):
#     model_config = ConfigDict(from_attributes=True)

#     id: UUID
#     context: str
#     title: str | None = None
#     tone: str
#     style: str
#     language: str
#     word_length: str
#     created_at: datetime
#     updated_at: datetime
#     status: str
#     publish_status: str

class QNAItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: UUID | None = None
    answer_id: UUID | None = None
    question_text: str | None = Field(default=None, alias='question')
    answer_text: str | None = Field(default=None, alias='answer')

class UserStoryResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # title: str | None = None
    context: str | None = None
    tone: str | None = None
    mode: str | None = None
    style: str | None = None
    language: str
    word_length: str | None
    created_at: datetime
    updated_at: datetime = None
    status: str
    publish_status: str = None

class UserStoryFullResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_story: UserStoryResponseSchema
    qna: list[QNAItem] = []
    generated: GeneratedStoryResponseSchema | None = None

class UserStoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: Optional[str] = None
    context: Optional[str] = None
    mode: str | None = None
    status: str = None
    publish_status: str = None
    initiated_at: Optional[datetime] = None
    slug: str | None = None
    generated_title: Optional[str] = None
    generated_snippet: Optional[str] = None
    images: Optional[list[dict] | None] = []
    generated_story_full_text: Optional[str] = None
    generated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EditGeneratedArticleSchema(BaseModel):
    title: str | None = Field(default=None, max_length=75)
    snippet: str | None = Field(default=None, min_length=30, max_length=2000)
    full_text: str | None = Field(default=None, min_length=500, max_length=100000)
    # images_keys: list[str] | None = Field(default=None, max_length=3, min_length=1)

class UploadedImageKeys(BaseModel):
    images_keys: list[str] | None = Field(None, max_length=3)

