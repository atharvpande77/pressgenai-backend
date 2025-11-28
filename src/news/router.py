from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload, selectinload
from sqlalchemy import select, func, case, literal
from sqlalchemy.dialects.postgresql import JSONB

from src.config.database import get_session
from src.models import GeneratedUserStories, NewsCategory, UserStories, UserStoryPublishStatus, Users, Authors
from src.news.dependencies import get_category_dep
from src.news.schemas import CreatorProfileResponse, ArticleResponse
from src.aws.utils import get_bucket_base_url, get_full_s3_object_url
from src.utils.query import get_article_images_json_query, get_profile_image_expression
from src.news.utils import get_category_name

router = APIRouter()

Creators = aliased(Users)
Editors = aliased(Users)

# creator_profile_image = case(
#         (Creators.profile_image_key != None,
#         func.concat(
#             literal(get_bucket_base_url()),
#             Creators.profile_image_key
#         )),
#         else_=None
#     ).label("creator_profile_image")

# editor_profile_image = case(
#         (Editors.profile_image_key != None,
#         func.concat(
#             literal(get_bucket_base_url()),
#             Editors.profile_image_key
#         )),
#         else_=None
#     ).label("editor_profile_image")

# images_json = func.coalesce(
#     func.json_agg(
#         func.json_build_object(
#             "key", func.unnest(GeneratedUserStories.images_keys),
#             "url", func.concat(get_bucket_base_url(), func.unnest(GeneratedUserStories.images_keys))
#         )
#     ),
#     func.cast("[]", JSONB)
# ).label("images")


@router.get('/', response_model=list[ArticleResponse])
async def get_all_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    category: Annotated[NewsCategory | None, Depends(get_category_dep)] = None,
    limit: Annotated[int | None, Query(gt=0, le=100)] = 10,
    offset: int| None = 0
):
    where_clause = (
        (GeneratedUserStories.category.contains([category]), UserStories.publish_status == UserStoryPublishStatus.PUBLISHED) 
        if category 
        else (UserStories.publish_status == UserStoryPublishStatus.PUBLISHED,)
    )

    result = await session.execute(
        select(
            GeneratedUserStories.id,
            GeneratedUserStories.title,
            GeneratedUserStories.snippet,
            GeneratedUserStories.full_text,
            GeneratedUserStories.created_at,
            GeneratedUserStories.updated_at,
            GeneratedUserStories.category,
            GeneratedUserStories.tags,
            GeneratedUserStories.slug,
            get_article_images_json_query(),
            Creators.username.label("creator_username"),
            Creators.first_name.label("creator_first_name"),
            Creators.last_name.label("creator_last_name"),
            get_profile_image_expression(Creators, "creator_profile_image"),
            Editors.first_name.label("editor_first_name"),
            Editors.last_name.label("editor_last_name"),
            get_profile_image_expression(Editors, "editor_profile_image")
        )
            .join(UserStories, onclause=UserStories.id == GeneratedUserStories.user_story_id)
            .join(Creators, onclause=Creators.id == GeneratedUserStories.author_id)
            .join(Editors, onclause=Editors.id == GeneratedUserStories.editor_id, isouter=True)
            .where(*where_clause)
            # .distinct()
            .limit(limit)
            .offset(offset)
            .order_by(GeneratedUserStories.published_at.desc())
    )
    
    # result = await session.execute(
    #     select(
    #         GeneratedUserStories.id,
    #         GeneratedUserStories.title, 
    #         GeneratedUserStories.snippet,
    #         GeneratedUserStories.category
    #     )
    #         .join(UserStories, onclause=UserStories.id==GeneratedUserStories.user_story_id)
    #         .join(Creators, onclause=Creators.id == GeneratedUserStories.author_id)
    #         .join(Editors, onclause=Editors.id == GeneratedUserStories.editor_id, isouter=True)
    #         .where(UserStories.publish_status == UserStoryPublishStatus.PUBLISHED)
    #         .limit(limit)
    #         .offset(offset)
    #         .order_by(GeneratedUserStories.published_at)
    # )
    articles = result.all()
    for article in articles:
        print({"id": article.id, "title": article.title, "snippet": article.snippet, "category": article.category})
    return articles


@router.get('/categories')
async def get_all_categories(lang: str | None = 'mr'):
    return [{"category_value": cat.value, "category_name": get_category_name(cat.value, lang=lang)} for cat in NewsCategory]


@router.get('/{article_slug}', response_model=ArticleResponse)
async def get_article_by_id(
    session: Annotated[AsyncSession, Depends(get_session)],
    article_slug: str
):
    
    result = await session.execute(
        select(
            GeneratedUserStories.id,
            GeneratedUserStories.title,
            GeneratedUserStories.snippet,
            GeneratedUserStories.full_text,
            GeneratedUserStories.created_at,
            GeneratedUserStories.updated_at,
            GeneratedUserStories.category,
            GeneratedUserStories.tags,
            GeneratedUserStories.slug,
            get_article_images_json_query(),
            Creators.username.label("creator_username"),
            Creators.first_name.label("creator_first_name"),
            Creators.last_name.label("creator_last_name"),
            get_profile_image_expression(Creators, label_name="creator_profile_image"),
            Editors.first_name.label("editor_first_name"),
            Editors.last_name.label("editor_last_name"),
            get_profile_image_expression(Editors, label_name="editor_profile_image")
        )
            .select_from(GeneratedUserStories)
            .join(Creators, onclause=Creators.id == GeneratedUserStories.author_id)
            .join(Editors, onclause=Editors.id == GeneratedUserStories.editor_id, isouter=True)
            .where(GeneratedUserStories.slug == article_slug)
            .limit(1)
    )
    article = result.first()
    if not article:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f'no article found for id {article_slug}'
        )
    
    return article

@router.get(
    '/creator/{username}',
    response_model=CreatorProfileResponse
)
async def get_creator_profile(
    session: Annotated[AsyncSession, Depends(get_session)],
    username: Annotated[str, Path(
        min_length=2,
        max_length=64,
        regex="^@[A-Za-z0-9._%+-]+$"
    )],
    sort_by: Annotated[str, Query(pattern="^(newest|oldest|popular)$")] = "newest"
):
    result = await session.execute(
        select(Authors)
            .where(Authors.user.has(username=username))
    )
    creator = result.scalars().first()
    
    if not creator:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="creator not found"
        )
    creator_user_db = creator.user
    creator_username = creator_user_db.username
    creator_first_name = creator_user_db.first_name
    creator_last_name = creator_user_db.last_name
    creator_profile_image = get_full_s3_object_url(creator_user_db.profile_image_key)

    articles_query = (
        select(
            GeneratedUserStories.id,
            GeneratedUserStories.title,
            GeneratedUserStories.snippet,
            GeneratedUserStories.full_text,
            GeneratedUserStories.created_at,
            GeneratedUserStories.updated_at,
            GeneratedUserStories.category,
            GeneratedUserStories.tags,
            GeneratedUserStories.slug,
            get_article_images_json_query(),
            Users.username.label("editor_username"),
            Users.first_name.label("editor_first_name"),
            Users.last_name.label("editor_last_name"),
            get_profile_image_expression(label_name="editor_profile_image")
        )
        .select_from(GeneratedUserStories)
        .outerjoin(Users, Users.id == GeneratedUserStories.editor_id)
        .where(
            GeneratedUserStories.user_story.has(publish_status=UserStoryPublishStatus.PUBLISHED),
            GeneratedUserStories.author_id == creator.id
        )
    )

    if sort_by == "newest" or sort_by == "popular":
        articles_query = articles_query.order_by(GeneratedUserStories.created_at.desc())
    elif sort_by == "oldest":
        articles_query = articles_query.order_by(GeneratedUserStories.created_at.asc())

    result = await session.execute(articles_query)
    articles = result.all()

    # print([article._asdict() for article in articles])

    return CreatorProfileResponse(
        username=creator_username,
        first_name=creator_first_name,
        last_name=creator_last_name,
        bio=creator.bio,
        profile_image=creator_profile_image,
        articles=articles
    )
