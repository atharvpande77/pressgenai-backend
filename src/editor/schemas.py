from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from uuid import UUID
from typing import Annotated

from src.models import NewsCategory


category_values = [category.value for category in NewsCategory]
class ArticleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    snippet: str | None = None
    full_text: str
    category: list[str] | None = []
    tags: list[str] | None = None
    created_at: datetime
    creator_username: str | None = None
    creator_first_name: str
    creator_last_name: str | None = None

class EditArticleSchema(BaseModel):
    title: Annotated[str | None, Field(min_length=10, max_length=75)] = None
    # snippet: Annotated[str | None, Field(min_length=100, max_length=1000)] = None
    full_text: Annotated[str | None, Field(min_length=1000, max_length=50000)] = None
    category: str | None = None
    tags: list[str] | None = []

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v is None:
            return v

        category_values = [category.value for category in NewsCategory]
        category_lower = v.lower()
        
        # Check if the lowercase version matches any category (case-insensitive)
        matching_category = next(
            (cat for cat in category_values if cat.lower() == category_lower),
            None
        )
        
        if matching_category is None:
            raise ValueError(
                f"Category must be one of: {', '.join(category_values)}"
            )
        
        # Return the properly cased version from the enum
        return matching_category
    

class RejectArticleSchema(BaseModel):
    reason: Annotated[str, Field(min_length=20, max_length=1200)]


class RejectedEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rejection_reason: str
    publish_status: str