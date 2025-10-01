from pydantic import BaseModel, EmailStr, ConfigDict, Field
from uuid import UUID

class CreateAuthorSchema(BaseModel):
    first_name: str = Field(max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr
    bio: str | None = Field(default=None, max_length=1500)
    password: str = Field(..., min_length=8, max_length=128, description="Password (8-128 characters)")

class AuthorResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    bio: str
    profile_image: str | None = None

class CreatorUpdatePasswordSchema(BaseModel):
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

class UpdateProfileSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=1500)