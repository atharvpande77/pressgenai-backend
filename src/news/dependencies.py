from enum import Enum
from fastapi import HTTPException, status

from src.models import NewsCategory

def get_category_dep(category: str | None = None):
    if category is None:
        return NewsCategory.GENERAL
    
    category = category.strip().lower()
    allowed_categories = [cat.value for cat in NewsCategory]
    if category not in allowed_categories:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(allowed_categories)}"
        )
    return category

