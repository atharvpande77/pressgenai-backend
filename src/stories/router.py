from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import Annotated, Literal
from sqlalchemy.ext.asyncio import AsyncSession
import traceback

from src.config.database import get_session
from src.schemas import LocationDataSchema, GenerateOptionsSchema, CreateStorySchema, QuestionsResponseSchema, AnswerSchema, GeneratedStoryResponseSchema, UserStoryFullResponseSchema, UserStoryItem, EditGeneratedArticleSchema, UploadedImageKeys,CreateStoryResponseSchema
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
    response_model=CreateStoryResponseSchema,
    summary="Create a new story (AI-assisted or manual writing mode)",
    description="""
        This endpoint initializes a new story draft for a creator.  

        The behavior depends on the selected mode:

        ---

        ### 🔹 AI-Assisted Mode (`mode="ai"`)

        The creator provides:
        - Context describing the incident or topic
        - Writing preferences (tone, style, language, length)

        The system stores the story and marks it as ready for:
        - Question generation (`GET /user/{id}/questions`)
        - Then full article generation (`GET /user/{id}/generate`)

        No article content is generated at this step.

        ---

        ### 🔹 Manual Mode (`mode="manual"`)

        The creator provides:
        - The complete article text
        - (Optional) title and images

        The system stores the content as-is. Metadata such as:
        - refined title (if needed)
        - snippet
        - tags
        - categories  

        will be generated later using the `GET /user/{id}/generate` endpoint.

        ---

        ### Workflow Result

        This endpoint returns the created story record and its current status.  
        No AI generation happens here.

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
        400: {
            "description": "Invalid input format or missing required fields",
            "content": {
                "application/json": {
                    "example": {"detail": "Validation error: context is required in ai mode"}
                }
            },
        },
        409: {
            "description": "Duplicate story detected",
            "content": {
                "application/json": {
                    "examples": {
                        "duplicate_title": {
                            "summary": "Duplicate manual article",
                            "value": {"detail": "You have already created a story with the same title."}
                        },
                        "duplicate_context": {
                            "summary": "Duplicate AI context",
                            "value": {"detail": "A story with the same context already exists."}
                        }
                    }
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
    user_story: UserStoryDep,
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
async def submit_answer(request: AnswerSchema, session: Session, user_story: UserStoryDep):
    if user_story.mode != 'ai':
        raise HTTPException(status_code=400, detail="User story is not in AI mode")
    return await upsert_answer(session, user_story.id, request)


@router.get(
    "/user/{user_story_id}/generate",
    response_model=GeneratedStoryResponseSchema,
    summary="Generate or retrieve the final article (AI-assisted or manual mode)",
    description="""
        This endpoint finalizes the user story into a publish-ready article.

        ### **How It Works**

        The behavior depends on the story's mode:

        ---

        #### 🔹 AI-Assisted Mode (`mode="ai"`)

        The system will:
        - Use the user's context, writing preferences (tone, style, language, length)
        - Use previously collected Q&A responses
        - Generate a full article including:  
        - Title (AI-generated if missing or weak)
        - Snippet (short HTML summary)
        - Complete formatted article body
        - Category
        - Tags

        ---

        #### 🔹 Manual Mode (`mode="manual"`)

        The user already provided the full written content.  
        The system will generate only the following metadata:

        - Improved title (only if missing or inaccurate)
        - Snippet (≤400 characters)
        - Category (1–3 best matches)
        - Tags (5–10 relevant keywords)

        **The full text is never rewritten in manual mode.**

        ---

        ### Retrieval and Regeneration Rules

        - If an article has already been generated and `force_regenerate=false`, the stored version is returned.
        - If `force_regenerate=true`, the article will be regenerated (content for AI mode or metadata for manual mode) and overwritten.

        ---

        ### Example Use Cases

        - ✔️ Creators reviewing drafts
        - ✔️ Editors regenerating metadata
        - ✔️ Article preview before submission

        """,
    responses={
        200: {"description": "Successfully generated or retrieved article"},
        400: {"description": "Invalid story mode"},
        404: {
            "description": "Required data missing (e.g., QnA missing for AI mode)"
        },
        409: {
            "description": "Duplicate article detected (slug/title conflict)"
        },
        502: {
            "description": "AI service error or model response could not be parsed"
        },
        500: {
            "description": "Database failure or unexpected internal server error"
        },
    },
)
async def generate_user_story(session: Session, user_story: UserStoryDep, force_regenerate: bool = False):
    # if user_story.mode != 'ai':
    #     raise HTTPException(status_code=400, detail="User story is not in AI mode")
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
    session: Session, generated_article: GeneratedArticleDep, request: UploadedImageKeys
):
    return await update_user_story_status(session, generated_article, request)