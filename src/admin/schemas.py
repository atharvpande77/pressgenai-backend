from pydantic import BaseModel, EmailStr, Field, model_validator, AliasPath, field_validator, ConfigDict
from typing import Self
from datetime import date
from uuid import UUID

from src.models import UserRoles
from src.creators.schemas import HighestEducation, WorkStatus, CreatorLink
from src.schemas import CategoriesDB, make_profile_image_mixin
from src.models import UserStoryPublishStatus

class NewUserSchema(BaseModel):
    email: EmailStr
    first_name: str = Field(max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=15)
    password: str = Field(min_length=8, max_length=128)
    role: UserRoles = Field(default=UserRoles.CREATOR)
    city_ids: list[UUID] = Field(default=[], max_length=3)
    category_ids: list[UUID] | None = Field(default=None)
    
    date_of_birth: date | None = Field(default=None)
    highest_education: HighestEducation | None = Field(default=None)
    work_status: WorkStatus | None = Field(default=None)
    education_other_specify: str | None = Field(default=None, max_length=20)
    work_status_other_specify: str | None = Field(default=None, max_length=20)
    links: list[CreatorLink] = Field(default=[])
    bio: str | None = Field(default=None, max_length=1500)

    @model_validator(mode='after')
    def validate_role_specific_fields(self) -> Self:
        if self.role == UserRoles.CREATOR:
            # Validate city_ids has exactly one city
            if len(self.city_ids) != 1:
                raise ValueError("CREATOR role must have exactly one city")
            
            # Validate category_ids is empty/None
            if self.category_ids:
                raise ValueError("CREATOR role cannot have category_ids")
            
            # Validate date_of_birth is provided
            if self.date_of_birth is None:
                raise ValueError("CREATOR role must have date_of_birth")
        
        elif self.role == UserRoles.EDITOR:
            # Check that creator-specific fields are not provided
            creator_fields = {
                'date_of_birth': self.date_of_birth,
                'highest_education': self.highest_education,
                'work_status': self.work_status,
                'education_other_specify': self.education_other_specify,
                'work_status_other_specify': self.work_status_other_specify,
                'links': self.links,
                'bio': self.bio
            }
            
            provided_fields = [
                field_name for field_name, value in creator_fields.items()
                if value is not None and (not isinstance(value, list) or len(value) > 0)
            ]
            
            if provided_fields:
                raise ValueError(
                    f"EDITOR role cannot have the following fields: {', '.join(provided_fields)}"
                )
        
        return self
    
    
class NewInvite(BaseModel):
    email: EmailStr
    first_name: str = Field(max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    role: UserRoles | None = Field(default=UserRoles.CREATOR)


ProfileImageMixin = make_profile_image_mixin("profile_image_key")


class AdminArticlePerson(ProfileImageMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class AdminPublishedArticleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    publish_status: str | None = Field(default=None, validation_alias=AliasPath("user_story", "publish_status"))
    creator: AdminArticlePerson = Field(validation_alias=AliasPath("author", "user"))
    editor: AdminArticlePerson | dict = Field(default_factory=dict)
    categories: list[CategoriesDB] = []

    @field_validator("editor", mode="before")
    @classmethod
    def normalize_editor(cls, v):
        return {} if v is None else v


class UpdateArticleStatusSchema(BaseModel):
    publish_status: UserStoryPublishStatus

    @model_validator(mode="after")
    def validate_allowed_status(self) -> Self:
        if self.publish_status not in [UserStoryPublishStatus.PUBLISHED, UserStoryPublishStatus.REJECTED]:
            raise ValueError("publish_status must be either 'published' or 'rejected'")
        return self
