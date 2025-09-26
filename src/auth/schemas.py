from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID

from src.authors.schemas import AuthorResponseSchema

class AuthSchema(BaseModel):
    email: EmailStr
    password: str

class UserResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str | None = None
    email: str
    role: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponseSchema