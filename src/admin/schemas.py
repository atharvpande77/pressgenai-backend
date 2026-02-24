from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Self
from datetime import date

from src.models import UserRoles
from src.creators.schemas import HighestEducation, WorkStatus, CreatorLink

class NewUserSchema(BaseModel):
    email: EmailStr
    first_name: str = Field(max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=15)
    password: str = Field(min_length=8, max_length=128)
    role: UserRoles | None = Field(default=UserRoles.CREATOR)
    city_ids: list[int] = Field(default=[], max_length=3)
    category_ids: list[int] | None = Field(default=[])
    
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
            
            # Validate category_ids is None
            if self.category_ids is not None:
                raise ValueError("CREATOR role cannot have category_ids (must be None)")
            
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