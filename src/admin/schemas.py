from pydantic import BaseModel, EmailStr, Field

class NewUserSchema(BaseModel):
    email: EmailStr
    first_name: str = Field(max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    password: str = Field(min_length=8, max_length=128)