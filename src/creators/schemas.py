from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from uuid import UUID

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

class AuthorResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    username: str | None
    bio: str | None
    profile_image: str | None = None

class CreatorUpdatePasswordSchema(BaseModel):
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

class UpdateProfileSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=1500)