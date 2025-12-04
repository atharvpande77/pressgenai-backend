from fastapi import Depends, status, HTTPException
from typing import Annotated, Literal

from src.stories.service import get_user_story_or_404
from src.models import UserStories

def user_story_mode_checker(mode: Literal["ai", "manual"]):
    def wrapper(user_story: Annotated[UserStories, Depends(get_user_story_or_404)]):
        if user_story.mode != mode:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"user story with id {user_story.id} is not in {mode} mode"
            )
        return user_story
    return wrapper