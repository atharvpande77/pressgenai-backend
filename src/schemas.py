from pydantic import BaseModel, field_validator, model_validator, ConfigDict, Field, HttpUrl, ConfigDict, field_serializer, computed_field, AliasChoices
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

from src.aws.utils import get_full_s3_object_url


def make_images_mixin(field_name: str = "images_keys"):
    class ImagesMixin:
        @field_validator(field_name, mode='before')
        @classmethod
        def normalize_images_keys(cls, v):
            if not v:
                return []
            normalized: list[str] = []
            for image in v:
                if isinstance(image, str):
                    normalized.append(image)
                elif isinstance(image, dict):
                    if image.get('key'):
                        normalized.append(image['key'])
                    elif image.get('url'):
                        normalized.append(image['url'])
            return normalized

        @computed_field
        @property
        def images(self) -> list[dict[str, str]] | None:
            keys = getattr(self, field_name, None)
            if not keys:
                return None
            return [
                {
                    "key": image,
                    "url": image if image.startswith(("http://", "https://")) else get_full_s3_object_url(image)
                }
                for image in keys
                if image
            ]

    ImagesMixin.__annotations__[field_name] = list[str]
    setattr(ImagesMixin, field_name, Field(default_factory=list, exclude=True, validation_alias=AliasChoices(field_name, 'images')))

    return ImagesMixin

ImagesMixIn = make_images_mixin('images_keys')

def make_profile_image_mixin(field_name: str = "profile_image_key"):
    class ProfileImageMixin:
        @computed_field
        @property
        def profile_image(self) -> dict[str, str] | None:
            key = getattr(self, field_name, None)
            if not key:
                return None
            return {
                "key": key,
                "url": key if key.startswith(("http://", "https://")) else get_full_s3_object_url(key)
            }

    # Dynamically add the field to the mixin
    ProfileImageMixin.__annotations__[field_name] = str | None
    setattr(ProfileImageMixin, field_name, Field(default=None, exclude=True))

    return ProfileImageMixin

ProfileImageMixin = make_profile_image_mixin('profile_image_key')
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
    # images_keys: list[str] = Field(default_factory=list)
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

    
class CategoriesDB(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    value: str    

class GeneratedStoryResponseSchema(ImagesMixIn, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    slug: str | None = None
    snippet: str | None = None
    full_text: str
    tags: list[str] | None = []
    categories: list[CategoriesDB] | None = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    
class CreateStoryBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    status: str
    publish_status: str
    mode: str

class CreateAIStoryResponse(CreateStoryBaseResponse):
    # AI mode fields
    context: str
    tone: str
    style: str
    language: str
    word_length: str
    
    
class CreateManualStoryResponse(ImagesMixIn, CreateStoryBaseResponse):
    title: str | None = None
    snippet: str | None = None
    full_text: str | None = None
    language: str | None = None

class QNAItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    context: Optional[str] = None
    mode: str | None = None
    status: str = None
    publish_status: str = None
    initiated_at: Optional[datetime] = None
    generated_title: Optional[str] = None
    generated_snippet: Optional[str] = None
    generated_story_full_text: Optional[str] = None
    generated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EditGeneratedArticleSchema(BaseModel):
    title: str | None = Field(default=None, max_length=ContentSizeLimits.TITLE_MAX)
    snippet: str | None = Field(default=None, min_length=ContentSizeLimits.SNIPPET_MIN, max_length=ContentSizeLimits.SNIPPET_MAX)
    full_text: str | None = Field(default=None, min_length=ContentSizeLimits.FULL_TEXT_MIN, max_length=ContentSizeLimits.FULL_TEXT_MAX)
    images_keys: list[str] | None = Field(default=[], max_length=3)

class UploadedImageKeys(BaseModel):
    images_keys: list[str] | None = Field(None, max_length=3)

