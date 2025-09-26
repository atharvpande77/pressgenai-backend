from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from uuid import UUID
from typing import Annotated

class ArticleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    snippet: str | None = None
    full_text: str
    created_at: datetime

class EditArticleSchema(BaseModel):
    title: Annotated[str, Field(min_length=10, max_length=75)]
    # snippet: Annotated[str | None, Field(min_length=100, max_length=1000)] = None
    full_text: Annotated[str, Field(min_length=1000, max_length=50000)]

class RejectArticleSchema(BaseModel):
    reason: Annotated[str, Field(min_length=20, max_length=1200)]


class RejectedEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rejection_reason: str
    publish_status: str