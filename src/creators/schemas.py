from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator, HttpUrl
from uuid import UUID
from enum import Enum
from datetime import datetime, date

class CreateAuthorSchema(BaseModel):
    first_name: str = Field(max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr
    bio: str | None = Field(default=None, max_length=1500)
    password: str = Field(..., min_length=8, max_length=128, description="Password (8-128 characters)")

    @field_validator('email')
    @classmethod
    def validate_email_length(cls, v: str) -> str:
        if len(v) > 254:
            raise ValueError('Email must be 254 characters or less')
        
        local_part = v.split('@')[0]
        if len(local_part) > 64:
            raise ValueError('Email local part must be 64 characters or less')
        
        return v
    

class CityResponseSchema(BaseModel):
    id: UUID | None = None
    name: str | None = None

class AuthorResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    username: str | None = None
    phone: str | None = None
    bio: str | None
    date_of_birth: date | None = None
    highest_education: str | None = None
    highest_education_other_specify: str | None = None
    work_status: str | None = None
    work_status_other_specify: str | None = None
    city: CityResponseSchema
    profile_image: str | None = None
    updated_at: datetime | None = None
    onboarding_completed: bool = False

class CreatorUpdatePasswordSchema(BaseModel):
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

class UpdateProfileSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=1500)
    
    
class HighestEducation(str, Enum):
    TENTH = "10th"
    TWELFTH = "12th"
    DIPLOMA = "diploma"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    POST_DOCTORAL = "post_doctoral"
    OTHER = "other"
    
class WorkStatus(str, Enum):
    STUDENT = "student"
    SELF_EMPLOYED = "self_employed"
    UNEMPLOYED = "unemployed"
    BUSINESS = "business"
    SALARIED = "salaried"
    FREELANCER = "freelancer"
    RETIRED = "retired"
    OTHER = "other"
    
class LinkType(str, Enum):
    SOCIAL_MEDIA = "social_media"
    BLOG = "blog"
    PORTFOLIO = "portfolio"
    WEBSITE = "website"
    OTHER = "other"
    
class CreatorLink(BaseModel):
    link_type: LinkType
    url: HttpUrl
    platform: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    
    @field_validator('platform')
    @classmethod
    def validate_platform(cls, v: str | None, info) -> str | None:
        if info.data.get('link_type') == LinkType.SOCIAL_MEDIA and not v:
            raise ValueError('Platform is required when link type is social media')
        return v
    

class CreatorOnboarding(BaseModel):
    city_id: UUID
    highest_education: HighestEducation
    work_status: WorkStatus
    education_other_specify: str | None = Field(default=None, max_length=20)
    work_status_other_specify: str | None = Field(default=None, max_length=20)
    links: list[CreatorLink] = Field(default=[])

    @field_validator('education_other_specify')
    @classmethod
    def validate_education_other(cls, v: str | None, info) -> str | None:
        if info.data.get('highest_education') == HighestEducation.OTHER and not v:
            raise ValueError('Please specify your education when selecting "other"')
        if info.data.get('highest_education') != HighestEducation.OTHER and v:
            raise ValueError('Specify field should only be provided when education is "other"')
        return v

    @field_validator('work_status_other_specify')
    @classmethod
    def validate_work_status_other(cls, v: str | None, info) -> str | None:
        if info.data.get('work_status') == WorkStatus.OTHER and not v:
            raise ValueError('Please specify your work status when selecting "other"')
        if info.data.get('work_status') != WorkStatus.OTHER and v:
            raise ValueError('Specify field should only be provided when work status is "other"')
        return v