from pydantic import BaseModel, Field
from typing import Annotated


class ArticleImagesRequest(BaseModel):
    filenames: Annotated[list[str], Field(..., max_length=3, min_length=1)]