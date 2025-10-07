from pydantic import BaseModel, field_validator, model_validator, ConfigDict, Field, HttpUrl, ConfigDict
from typing import Literal, Optional, Annotated
from uuid import UUID
from datetime import datetime
from enum import Enum

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
    AI_ASSISTED = "ai_assisted"

class CreateStorySchema(BaseModel):
    title: Annotated[str, Field(max_length=75)] = ""
    context: str = Field(..., min_length=50, max_length=1200)
    options: GenerateOptionsSchema
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v and len(v) < 10:
            raise ValueError('Title must be at least 10 characters long when provided')
        return v

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
    question_type: Literal["what", "who", "where", "why", "when", "how", "sources"]
    question_text: str

class AnswerSchema(BaseModel):
    question_id: str
    answer_text: str

class GeneratedStoryResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    slug: str | None = None
    snippet: str | None = None
    full_text: str | None = None
    category: list[str] = []
    tags: list[str] | None = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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
    title: str | None = None
    context: str
    tone: str
    style: str
    language: str
    word_length: str
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
    status: str = None
    publish_status: str = None
    initiated_at: Optional[datetime] = None
    generated_title: Optional[str] = None
    generated_snippet: Optional[str] = None
    generated_story_full_text: Optional[str] = None
    generated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EditGeneratedArticleSchema(BaseModel):
    title: str | None = Field(default=None, max_length=75)
    snippet: str | None = Field(default=None, min_length=30, max_length=900)
    full_text: str | None = Field(default=None, min_length=900, max_length=100000)

