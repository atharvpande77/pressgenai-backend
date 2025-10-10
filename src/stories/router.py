from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import Annotated, Literal
from sqlalchemy.ext.asyncio import AsyncSession
import traceback
from uuid import UUID

from src.config.database import get_session
from src.schemas import LocationDataSchema, GenerateOptionsSchema, CreateStorySchema, QuestionsResponseSchema, AnswerSchema, GeneratedStoryResponseSchema, UserStoryFullResponseSchema, UserStoryItem, EditGeneratedArticleSchema, UploadedImageKeys
from src.stories.service import add_stories_to_db, get_location_status, fetch_stories_from_db, add_location_record, update_location_timestamp, get_story_by_id, create_user_story_db, get_generated_user_story, upsert_answer, generate_and_store_story_questions, get_user_story_or_404, update_user_story_status, get_user_stories_db, get_complete_story_by_id, edit_generated_article_db
from src.stories.utils import needs_fetching, fetch_news_articles, rewrite_story, get_all_news, get_story_status_dep
from src.models import UserStories, Users, UserRoles, GeneratedUserStories
from src.auth.dependencies import role_checker
from src.media.service import check_article_authorization

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
UserStoryDep = Annotated[UserStories, Depends(get_user_story_or_404)]
GeneratedArticleDep = Annotated[GeneratedUserStories, Depends(check_article_authorization)]

@router.get("/", include_in_schema=False)
async def get_feed():
    feed = await get_all_news()
    return feed

@router.post('/', include_in_schema=False)
async def get_news_feed(request: LocationDataSchema, session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        location_db = await get_location_status(session, request)
        if not location_db:
            news_articles = await fetch_news_articles(request)
            added_location = await add_location_record(session, request)
            added_articles = await add_stories_to_db(session, news_articles, added_location.id)
            return {
                'stories': added_articles,
                'count': len(added_articles)
            }
        if needs_fetching(location_db):
            news_articles = await fetch_news_articles(request, since_timestamp=location_db.last_fetched_timestamp)
            await update_location_timestamp(session, location_db.id)

            if news_articles:
                await add_stories_to_db(session, news_articles, location_db.id)
        
        all_articles = await fetch_stories_from_db(session, location_db.id)
        return {
                'stories': all_articles,
                'count': len(all_articles)
            }
        
    except ValueError as ve:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"Error in get_news_feed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail="An error occurred while fetching news articles"
        )
        
@router.patch('/select/{id}', include_in_schema=False)
async def select_story(id, session: Annotated[AsyncSession, Depends(get_session)]):
    ...

@router.post('/generate/{id}', include_in_schema=False)
async def generate_article(id: str, options: GenerateOptionsSchema, session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        print(f"Generate options: {options}")
        story = await get_story_by_id(session, id)
        if not story:
            return HTTPException(status_code=404, detail="story not found")
        
        generated_story = await rewrite_story(options, story)
        if not generated_story:
            return HTTPException(status_code=500, detail="cannot generate a new story at the moment")
        # print(f"Generated story: {generated_story}\nType of generated story: {type(generated_story)}")
        return generated_story

    except Exception as e:
        print(e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail="An error occurred while generating the story"
        )


# @router.post('/res')
# async def get_gpt_response(request: ReqSchema):
#     try:
#         response = await get_prompt_response(request)
#         return {
#             "response": response
#         }

#     except Exception as e:
#         print(e)
#         return HTTPException(
#             status_code=500,
#             detail=str(e)
#         )


@router.get(
    "/user",
    response_model=list[UserStoryItem],
    summary="List all user stories",
    description="""
        Fetch a paginated list of user stories created by status ('draft', 'submitted', 'rejected' or 'published').  
        Supports `limit` and `offset` for pagination.
        Returns with limit=10 and offset=0 by default
    """
)
async def get_user_stories_by_status(session: Session, status: Annotated[Literal['draft', 'submitted', 'rejected', 'published'], Depends(get_story_status_dep)], curr_creator: Annotated[Users, Depends(role_checker('creator'))], limit: int | None = 10, offset: int | None = 0):
    return await get_user_stories_db(
        session,
        curr_creator.id,
        status,
        limit,
        offset
    )


@router.get(
    "/user/{user_story_id}",
    response_model=UserStoryFullResponseSchema,
    summary="Retrieve a specific user story",
    description="""
        Get details of a single user story by its ID.  
        Includes metadata such as title, tone, style, language, and context.
        """
)
async def get_user_story(session: Session, curr_creator: Annotated[Users, Depends(role_checker('creator'))], user_story_id: str):
    return await get_complete_story_by_id(session, user_story_id, curr_creator.id)


@router.post(
    "/user",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user story",
    description="""
    Create a new user story configuration.  

    A story contains metadata such as:
    - `title` (optional)
    - `context` (required, describes the incident/news)
    - `tone` (e.g., formal, casual, neutral)
    - `style` (e.g., informative, narrative, breaking news)
    - `language` (default: English)
    - `word_length` (numeric target, e.g., 300, 800)
    - `word_length_range` (automatically derived from length)  

    This is the first step before generating contextual questions or articles.
    """,
        responses={
            201: {
                "description": "User story successfully created",
                "content": {
                    "application/json": {
                        "example": {
                            "id": "8c8617b5-9210-4d94-8c52-3a77f813ed1e",
                            "status": "created",
                            "title": "Floods in Maharashtra",
                            "context_preview": "Heavy rainfall has caused severe flooding in...",
                            "tone": "formal",
                            "style": "informative",
                            "language": "English",
                            "word_length": 500,
                            "word_length_range": "500–800"
                        }
                    }
                },
            },
            400: {
                "description": "Bad request (invalid input format)",
                "content": {
                    "application/json": {
                        "example": {"detail": "Request validation error: tone must be a string"}
                    }
                },
            },
            409: {
                "description": "Conflict (duplicate context or title)",
                "content": {
                    "application/json": {
                        "example": {"detail": "A story with the same context or title already exists."}
                    }
                },
            },
            500: {
                "description": "Internal server error (unexpected failure)",
                "content": {
                    "application/json": {
                        "example": {"detail": "An unexpected error occurred while creating the story."}
                    }
                },
            },
        },
)
async def create_new_story(
    request: CreateStorySchema,
    session: Annotated[AsyncSession, Depends(get_session)],
    curr_creator: Annotated[Users, Depends(role_checker(UserRoles.CREATOR))]
):
    return await create_user_story_db(session, request, curr_creator.id)


@router.get(
    "/user/{user_story_id}/questions",
    response_model=list[QuestionsResponseSchema],
    summary="Generate or retrieve contextual questions",
    description="""
        Fetch all contextual questions (5W1H + sources) linked to a user story.  

        - If `force_regenerate=false` (default), return existing questions if available.  
        - If `force_regenerate=true`, regenerate fresh questions and overwrite old ones.  
        Questions help structure the answers that will guide article generation.
    """,
    responses={
        404: {
            "description": "User story not found",
            "content": {
                "application/json": {
                    "example": {"detail": "User story not found"}
                }
            },
        },
        500: {
            "description": "Internal server error (DB error or parsing issue)",
            "content": {
                "application/json": {
                    "example": {"detail": "DB error: could not insert questions"}
                }
            },
        },
        502: {
            "description": "External AI service error",
            "content": {
                "application/json": {
                    "example": {"detail": "openai service error"}
                }
            },
        },
    }
)
async def get_context_questions(
    session: Session,
    user_story: UserStoryDep,
    force_regenerate: bool = False
):
    return await generate_and_store_story_questions(session, user_story.id, force_regenerate)


@router.post(
    "/user/{user_story_id}/answer",
    summary="Submit or update an answer for a question",
    description="""
        Submit an answer to one of the contextual questions linked to a user story.  

        - Uses `upsert` behavior: if the answer exists for a given `question_id`, it is updated.  
        - Otherwise, a new answer is created.  

        This step is required before article generation.
    """,
    responses={
        200: {
            "description": "Answer stored successfully",
            "content": {
                "application/json": {
                    "example": {"status": "success", "answer_id": "8d27e12b-9c92-4c3a-81d0-76c5bcb2b53c"}
                }
            },
        },
        404: {
            "description": "Question not found in this user story",
            "content": {
                "application/json": {
                    "example": {"detail": "Question not found for this user story"}
                }
            },
        },
        400: {
            "description": "Bad request (invalid data, constraint violation)",
            "content": {
                "application/json": {"example": {"detail": "Invalid data or constraint violation"}}
            },
        },
        500: {
            "description": "Unexpected server error",
            "content": {
                "application/json": {"example": {"detail": "Could not store answer at the moment"}}
            },
        },
    },
)
async def submit_answer(request: AnswerSchema, session: Session, user_story: UserStoryDep):
    return await upsert_answer(session, user_story.id, request)


@router.get(
    "/user/{user_story_id}/generate",
    response_model=GeneratedStoryResponseSchema,
    summary="Generate an AI-written article",
    description="""
        Generate the final AI-written article based on:  
        - User story metadata (tone, style, language, word count target)  
        - Context provided  
        - Answers to contextual questions  

        - If `force_regenerate=false` (default), return the cached/generated article if available.  
        - If `force_regenerate=true`, regenerate the article from scratch.  

        The response includes:  
        - `title` (AI-generated if user did not provide one)  
        - `snippet` (short 2–3 sentence HTML summary)  
        - `full_text` (complete article in HTML format with structured headings and paragraphs).
        """,
    responses={
        404: {"description": "QnA not found for the given user story"},
        502: {"description": "Error during AI generation or JSON parsing"},
        500: {"description": "Database error or unexpected server error"},
    },
)
async def generate_user_story(session: Session, user_story: UserStoryDep, force_regenerate: bool = False):
    return await get_generated_user_story(session, user_story, force_regenerate)


@router.put("/user/generate/{generated_article_id}", response_model=GeneratedStoryResponseSchema)
async def edit_generated_article(session: Session, curr_creator: Annotated[Users, Depends(role_checker(UserRoles.CREATOR))], generated_article_id: str, payload: EditGeneratedArticleSchema):
    return await edit_generated_article_db(session, curr_creator.id, generated_article_id, payload)


@router.patch(
    "/user/{generated_article_id}",
    summary="Change story status to submitted",
    description="""
    Update the status of a specific user story to **SUBMITTED**.  
    This is typically called when the user has finished providing all answers 
    and is ready for editorial review.
    """,
    responses={
        404: {"description": "User story not found"},
        500: {"description": "Database error while updating story status"},
    },
)
async def change_story_status_to_submitted(
    session: Session, generated_article: GeneratedArticleDep, request: UploadedImageKeys | None = Body(default=None)
):
    return await update_user_story_status(session, generated_article, request)





