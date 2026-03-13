from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import Annotated, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from src.config.database import get_session
from src.schemas import LocationDataSchema, GenerateOptionsSchema, CreateStorySchema, QuestionsResponseSchema, AnswerSchema, GeneratedStoryResponseSchema, UserStoryFullResponseSchema, UserStoryItem, EditGeneratedArticleSchema,CreateAIStoryResponse, CreateManualStoryResponse
from src.stories.service import add_stories_to_db, get_location_status, fetch_stories_from_db, add_location_record, update_location_timestamp, get_story_by_id, create_user_story_db, get_generated_user_story, upsert_answer, generate_and_store_story_questions, get_user_story_or_404, update_user_story_status, get_user_stories_db, get_complete_story_by_id, edit_generated_article_db
from src.stories.utils import needs_fetching, fetch_news_articles, rewrite_story, get_all_news, get_story_status_dep
from src.models import UserStories, Users, UserRoles, GeneratedUserStories, UserStoryStatus
from src.auth.dependencies import role_checker
from src.media.service import check_article_authorization
from src.stories.dependencies import user_story_mode_checker

router = APIRouter()
logger = logging.getLogger(__name__)
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
        logger.warning("Invalid request for news feed", extra={"event": "news_feed.validation"})
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        logger.exception("Unexpected error while fetching news feed", extra={"event": "news_feed.failure"})
        raise HTTPException(
            status_code=500,
            detail="An error occurred while fetching news articles"
        )
        


@router.post('/generate/{id}', include_in_schema=False)
async def generate_article(id: str, options: GenerateOptionsSchema, session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        logger.debug("Generate article options", extra={"event": "story.generate.options", "options": options})
        story = await get_story_by_id(session, id)
        if not story:
            return HTTPException(status_code=404, detail="story not found")
        
        generated_story = await rewrite_story(options, story)
        if not generated_story:
            return HTTPException(status_code=500, detail="cannot generate a new story at the moment")
        # print(f"Generated story: {generated_story}\nType of generated story: {type(generated_story)}")
        return generated_story

    except Exception:
        logger.exception("Error during story generation", extra={"event": "story.generate.failure", "user_story_id": id})
        raise HTTPException(
            status_code=500,
            detail="An error occurred while generating the story"
        )
        

@router.get(
    "/user",
    response_model=list[UserStoryItem],
    summary="List all user stories by status",
    description="""Fetch a paginated list of user stories filtered by status.
    
    Filters stories by one of four statuses:
    - 'draft': Stories in draft state (not yet submitted)
    - 'submitted': Stories submitted for editor review
    - 'rejected': Stories rejected by editors with feedback
    - 'published': Stories approved and published
    
    Supports pagination with limit (default 10) and offset (default 0) parameters.
    Only returns stories created by the authenticated creator.""",
    responses={
        200: {"description": "Successfully retrieved stories list"},
        401: {"description": "Insufficient permissions - Creator role required"},
        400: {"description": "Invalid status parameter"},
        500: {"description": "Internal server error while fetching stories"}
    }
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
    summary="Retrieve complete user story details",
    description="""Fetch detailed information about a specific user story.
    
    Returns comprehensive story metadata:
    - Story mode (ai or manual) and current status
    - Story context, tone, style, language preferences
    - Word length and publication status
    - Associated generated article (if available)
    - Creation and update timestamps
    
    Only the story creator can retrieve their own stories.""",
    responses={
        200: {"description": "Successfully retrieved story details"},
        401: {"description": "Insufficient permissions - Creator role required"},
        403: {"description": "Cannot retrieve another creator's story"},
        404: {"description": "User story not found"},
        500: {"description": "Internal server error while fetching story"}
    }
)
async def get_user_story(session: Session, curr_creator: Annotated[Users, Depends(role_checker('creator'))], user_story_id: str):
    return await get_complete_story_by_id(session, user_story_id, curr_creator.id)


@router.post(
    "/user",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateAIStoryResponse | CreateManualStoryResponse,
    summary="Create a new story draft (AI or manual mode)",
    description="""
        Create a creator-owned story record in one of two modes.

        AI mode (`mode="ai"`):
        - Stores story context and writing preferences (tone/style/language/word_length).
        - Does not generate article text at this step.
        - Typical next flow: `/user/{user_story_id}/questions`, answer submission, then `/user/{user_story_id}/generate`.

        Manual mode (`mode="manual"`):
        - Stores the provided draft immediately (`title`, `full_text`, `images_keys`).
        - Metadata generation (snippet/tags/categories/title refinement) happens later via `/user/{user_story_id}/generate`.

        Returns the created draft with status and mode-specific payload.
        """,
    responses={
        201: {
            "description": "Story successfully created",
            "content": {
                "application/json": {
                    "example": {
                        "id": "8c8617b5-9210-4d94-8c52-3a77f813ed1e",
                        "mode": "ai",
                        "status": "collecting",
                        "publish_status": "draft",
                        "context": "Heavy rainfall has caused severe flooding in...",
                        "tone": "formal",
                        "style": "informative",
                        "language": "English",
                        "word_length": 600
                    }
                }
            },
        },
        422: {
            "description": "Validation error in request body",
            "content": {
                "application/json": {
                    "example": {"detail": [{"loc": ["body", "context"], "msg": "Field required", "type": "missing"}]}
                }
            },
        },
        409: {
            "description": "Duplicate story detected",
            "content": {
                "application/json": {
                    "example": {"detail": "A story with the same title, body, or context already exists."}
                }
            },
        },
        500: {
            "description": "Internal error while saving the story",
            "content": {
                "application/json": {
                    "example": {"detail": "An unexpected server error occurred while creating the story."}
                }
            },
        },
    },
)
async def initiate_new_story(
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
    user_story: Annotated[UserStories, Depends(user_story_mode_checker("ai"))],
    force_regenerate: bool = False
):
    return await generate_and_store_story_questions(session, user_story, force_regenerate)


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
async def submit_answer(request: AnswerSchema, session: Session, user_story: Annotated[UserStories, Depends(user_story_mode_checker("ai"))]):
    if user_story.mode != 'ai':
        raise HTTPException(status_code=400, detail="User story is not in AI mode")
    return await upsert_answer(session, user_story.id, request)


@router.get(
    "/user/{user_story_id}/generate",
    response_model=GeneratedStoryResponseSchema,
    summary="Generate or fetch generated story output",
    description="""
        Generate and persist story output based on the story mode.

        AI mode (`mode="ai"`):
        - Requires stored QnA for the story.
        - Generates article content and metadata (title/snippet/full_text/tags/categories).

        Manual mode (`mode="manual"`):
        - Requires an existing manual draft with `title` and `full_text`.
        - Generates metadata for that draft (title refinement/snippet/tags/categories).
        - The draft body is not rewritten.

        Retrieval behavior:
        - If a generated article already exists and story status is `generated`, it is returned when `force_regenerate=false`.
        - Otherwise generation runs and stored data is updated.
        """,
    responses={
        200: {"description": "Successfully generated or retrieved article"},
        400: {
            "description": "Invalid mode data or missing prerequisites in manual mode",
            "content": {
                "application/json": {
                    "examples": {
                        "manual_missing_article": {
                            "summary": "Manual article missing",
                            "value": {"detail": "Manual mode requires an existing generated article"}
                        },
                        "manual_missing_required_fields": {
                            "summary": "Title/full_text missing",
                            "value": {"detail": "Title and full text must be present before generating metadata"}
                        },
                        "invalid_mode": {
                            "summary": "Unsupported mode",
                            "value": {"detail": "Invalid story mode"}
                        }
                    }
                }
            },
        },
        404: {
            "description": "Story or required AI inputs not found",
            "content": {
                "application/json": {
                    "examples": {
                        "story_not_found": {
                            "summary": "Story not found",
                            "value": {"detail": "User story not found"}
                        },
                        "missing_qna": {
                            "summary": "No QnA found",
                            "value": {"detail": "No QnA found for this story"}
                        }
                    }
                }
            },
        },
        502: {
            "description": "AI service error or generation parsing failure",
            "content": {
                "application/json": {
                    "example": {"detail": "Error while generating article or JSON parsing"}
                }
            },
        },
        500: {
            "description": "Database failure or unexpected internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Error while storing generated article in DB"}
                }
            },
        },
    },
)
async def generate_user_story(session: Session, user_story: UserStoryDep, force_regenerate: bool = False):
    return await get_generated_user_story(session, user_story, force_regenerate)


@router.put(
    "/user/generate/{generated_article_id}",
    response_model=GeneratedStoryResponseSchema,
    summary="Edit generated article content",
    description="""Update the title, snippet, full text, images, and metadata of a generated article.
    
    Only articles in DRAFT or GENERATED status can be edited.
    Submitted articles cannot be modified - they must be rejected first.
    
    Editable fields:
    - title: Article headline
    - snippet: Short summary
    - full_text: Complete article body
    - images_keys: S3 image keys for article media
    - tags: Array of article tags
    - categories: Array of category IDs
    - city: City ID for article location
    
    Only the creator who owns the story can edit their articles.""",
    responses={
        200: {"description": "Article successfully updated"},
        400: {"description": "Invalid request data or article in non-editable state"},
        401: {"description": "Insufficient permissions - Creator role required"},
        403: {"description": "Cannot edit another creator's articles"},
        404: {"description": "Article not found"},
        500: {"description": "Database error while updating article"}
    }
)
async def edit_generated_article(
    session: Session,
    curr_creator: Annotated[Users, Depends(role_checker(UserRoles.CREATOR))], generated_article_id: str,
    payload: EditGeneratedArticleSchema
):
    return await edit_generated_article_db(
        session,
        curr_creator.id,
        generated_article_id,
        payload
    )


@router.patch(
    "/user/{generated_article_id}",
    summary="Submit story for editor review",
    description="""Submit a generated article for editor review and publication consideration.
    
    Transitions the story status from GENERATED to SUBMITTED, marking it as ready for editorial review.
    
    Prerequisites before submission:
    - Story must have status GENERATED (generated article must exist)
    - Article must have a non-empty title
    - Article must have complete full_text content
    - Only article creator can submit their own stories
    
    Once submitted, the article cannot be edited directly - editors may request changes via rejection.""",
    responses={
        200: {"description": "Story successfully submitted for review"},
        400: {"description": "Title and article body must be present before submitting"},
        401: {"description": "Insufficient permissions - Creator role required"},
        403: {"description": "Cannot submit another creator's stories"},
        404: {"description": "Generated article not found"},
        409: {"description": "Can only submit articles with GENERATED status"},
        500: {"description": "Database error while updating story status"}
    }
)
async def change_story_status_to_submitted(
    session: Session,
    generated_article: GeneratedArticleDep
):
    user_story = generated_article.user_story
    story_status = user_story.status
    
    if story_status != UserStoryStatus.GENERATED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Can only submit generated articles"
        )
    
    if not generated_article.title or not generated_article.full_text:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Title and article body must be present before submitting"
        )
    
    await update_user_story_status(
        session,
        user_story_id=generated_article.user_story_id,
        submitted_at=datetime.now()
    )
    
    await session.commit()
    
    return {"status": "success"}
    
