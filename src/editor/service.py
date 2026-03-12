from src.models import UserStories, UserStoryStatus, GeneratedUserStories, UserStoryPublishStatus, Users, UserRoles, Authors, EditorCategories, EditorCities, ArticleCategories, Categories, Cities
from src.editor.schemas import EditArticleSchema, ArticleItem
from src.utils.query import get_article_images_json_query, get_profile_image_expression, get_creator_profile_image
from src.creators.utils import hash_password
from src.editor.schemas import CreatorItem, CreateCreatorSchema
from src.aws.utils import get_images_with_urls
from src.auth.utils import verify_pw

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy import select, update, delete, or_, and_, func, literal, case, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased, selectinload, contains_eager
from fastapi import HTTPException, status
import traceback
from uuid import UUID
from datetime import datetime, timedelta


Creators = aliased(Users)
Editors = aliased(Users)

async def get_articles_by_publish_status(session: AsyncSession, editor_status: str, curr_editor_id: UUID, limit: int = 10, offset: int = 0):
    try:
        query = text("""
            SELECT
                gus.id,
                gus.title,
                us.publish_status,
                -- Aggregate all matching categories into a JSON array
                json_agg(
                    json_build_object(
                        'id',  c.id,
                        'name',  c.name,
                        'value', c.value
                    )
                ) AS categories,
                gus.city_id,
                ct.name AS city,
                -- Creator as JSON
                json_build_object(
                    'id', cu.id,
                    'first_name', cu.first_name,
                    'last_name', cu.last_name,
                    'username', cu.username,
                    'profile_image_key', cu.profile_image_key
                ) AS creator,
                -- Editor as JSON (empty object if null)
                COALESCE(
                    json_build_object(
                        'id', eu.id,
                        'first_name', eu.first_name,
                        'last_name', eu.last_name,
                        'username', eu.username,
                        'profile_image_key', eu.profile_image_key
                    ),
                    '{}'::json
                ) AS editor,
                
                -- Can edit flag
                CASE 
                    WHEN gus.editor_id IS NULL OR gus.editor_id = :curr_editor_id
                    THEN true
                    ELSE false
                END AS can_edit,
                
                us.submitted_at,
                gus.published_at
                
            FROM generated_user_stories gus
            JOIN user_stories us
                ON gus.user_story_id = us.id
            JOIN article_categories ac
                ON ac.article_id = gus.id
            JOIN categories c
                ON c.id = ac.category_id
            JOIN cities ct
                ON ct.id = gus.city_id
            JOIN users cu
                ON cu.id = gus.author_id
                
            LEFT JOIN users eu
                ON eu.id = gus.editor_id
            LEFT JOIN editor_categories ec
                ON ec.editor_id = :curr_editor_id
                AND ec.category_id = ac.category_id
            JOIN editor_cities ecc
                ON ecc.editor_id = :curr_editor_id
                AND ecc.city_id = gus.city_id
            WHERE
                us.publish_status = :editor_status
                AND us.status = :submitted_status
                AND (
                    gus.editor_id IS NULL
                    OR gus.editor_id = :curr_editor_id
                )
                AND cu.active = true
            GROUP BY
                gus.id,
                gus.title,
                us.publish_status,
                gus.city_id,
                ct.name,
                gus.author_id,
                cu.id,
                cu.first_name,
                cu.last_name,
                cu.username,
                cu.profile_image_key,
                gus.editor_id,
                eu.id,
                eu.first_name,
                eu.last_name,
                eu.username,
                eu.profile_image_key,
                us.submitted_at,      
                gus.published_at
            ORDER BY MAX(gus.created_at) DESC
            LIMIT :limit
            OFFSET :offset;
        """)

        result = await session.execute(query, {
            "curr_editor_id": str(curr_editor_id),
            "editor_status": editor_status,
            "submitted_status": UserStoryStatus.SUBMITTED,
            "limit": limit,
            "offset": offset
        })
        articles = result.mappings().all()
        
        # print(articles)
        return articles
    except DatabaseError as e:
        msg = f'Error while {editor_status} fetching articles'
        print(msg)
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={
            "msg": msg,
            "error": str(e)
        })
    
async def get_article_by_id_db(
    session: AsyncSession,
    article_id: UUID
):
    article = await session.get(GeneratedUserStories, article_id)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'no article found for id {article_id}')
    return article


async def get_editor_profile_info(
    session: AsyncSession,
    editor_id: UUID
):
    editor = await session.get(Users, editor_id)
    if not editor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="editor not found")

    categories_query = await session.execute(
        select(Categories)
            .join(EditorCategories, EditorCategories.category_id == Categories.id)
            .where(EditorCategories.editor_id == editor_id)
    )
    categories = categories_query.scalars().all()

    cities_query = await session.execute(
        select(Cities)
            .join(EditorCities, EditorCities.city_id == Cities.id)
            .where(EditorCities.editor_id == editor_id)
    )
    cities = cities_query.scalars().all()

    return editor, categories, cities


async def update_editor_password(
    session: AsyncSession,
    curr_editor: Users,
    old_password: str,
    new_password: str
):
    if not verify_pw(old_password, curr_editor.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="incorrect password"
        )
    new_hashed_password = hash_password(new_password)

    try:
        await session.execute(
            update(Users).where(Users.id == curr_editor.id).values(password=new_hashed_password)
        )
        await session.commit()
        return {"status": "success"}
    except Exception as e:
        await session.rollback()
        msg = str(e)
        print(f"Unknown error while updating password: {msg}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=msg
        )

async def edit_article_db(
    session: AsyncSession,
    article_id: UUID,
    values: dict
):
    values = dict(values)
    category_ids = values.pop("categories", None)
    column_values = {
        key: values[key]
        for key in ("title", "snippet", "full_text", "tags", "images_keys", "location_scope", "city_id")
        if key in values
    }
    updated_story = None

    if column_values:
        result = await session.execute(
            update(GeneratedUserStories)
                .where(GeneratedUserStories.id == article_id)
                .values(**column_values)
                .returning(GeneratedUserStories)
        )
        updated_story = result.scalars().first()

    if category_ids is not None:
        await store_article_categories(
            session=session,
            article_id=article_id,
            category_ids=category_ids
        )

    result = await session.execute(
        select(GeneratedUserStories)
            .where(GeneratedUserStories.id == article_id)
            .options(selectinload(GeneratedUserStories.categories))
            .execution_options(populate_existing=True)
    )
    updated_story = result.scalars().first()
    return updated_story

    # article_id = article.id
    # values = payload.model_dump(exclude_none=True)
    # if not values:
    #     raise HTTPException(
    #         status.HTTP_400_BAD_REQUEST,
    #         detail="all fields cannot be empty"
    #     )
        
    # # print(f"Editing article: {values}")
        
    # result = await session.execute(
    #     update(GeneratedUserStories)
    #         .where(GeneratedUserStories.id == article_id)
    #         .values(editor_id=curr_editor_id, **values)
    #         .returning(GeneratedUserStories)
    # )
    # article_updated = result.scalars().first()
    
    # if article.user_story.publish_status == UserStoryPublishStatus.PENDING:
    #     await set_publish_status(
    #         session, article.user_story_id, UserStoryPublishStatus.WORK_IN_PROGRESS
    #     )
        
    # await session.commit()
    
    # article_updated.images = get_images_with_urls(article_updated.images_keys)
    
    # return article_updated
    
    # stmt = update(GeneratedUserStories).where(GeneratedUserStories.id == article_id).values(values).returning(GeneratedUserStories)
    # result = await session.execute(stmt)
    # article_db = result.scalars().first()
    # if not article_db:
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'no article found for id {article_id}')
    # publish_status = await set_publish_status(session, article_db.user_story_id, UserStoryPublishStatus.PUBLISHED)
    # await session.commit()
    # return {'msg': "success", 'article_id': article_id, 'publish_status': publish_status}


async def set_publish_status(
    session: AsyncSession,
    user_story_id: UUID,
    article_id: UUID,
    new_publish_status: str,
    curr_editor_id: UUID,
    params: dict | None = None
):
    await session.execute(
        update(UserStories)
            .where(UserStories.id == user_story_id)
            .values(publish_status=new_publish_status)
    )
    
    published_at = datetime.now()+timedelta(hours=5, minutes=30) if new_publish_status == UserStoryPublishStatus.PUBLISHED else None
    
    update_fields = {"editor_id": curr_editor_id}
    if published_at:
        update_fields["published_at"] = published_at
        
    if params:
        update_fields = {**update_fields, **params}
    
    await session.execute(
        update(GeneratedUserStories)
            .where(
                GeneratedUserStories.user_story_id == user_story_id,
                GeneratedUserStories.id == article_id
            )
            .values(update_fields)
    )
    
    # if published_at:
    #     await session.execute(
    #         update(GeneratedUserStories)
    #             .where(GeneratedUserStories.user_story_id == user_story_id)
    #             .values(published_at=published_at)
    #     )
    # await session.commit()
    # return publish_status

async def _set_editor_id(session: AsyncSession, article: GeneratedUserStories, editor_id: str):
    if not article.editor_id:
        await session.execute(update(GeneratedUserStories).values(editor_id=editor_id).where(GeneratedUserStories.id == article.id))
        return True
    return False

async def publish_article_db(session: AsyncSession, article: GeneratedUserStories, curr_editor_id: UUID):
    publish_status = await set_publish_status(session, article.user_story_id, UserStoryPublishStatus.PUBLISHED)
    if not publish_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no story found for this generated article')
    
    await session.execute(
        update(GeneratedUserStories)
            .values(editor_id=curr_editor_id)
            .where(GeneratedUserStories.id == article.id)
    )
    
    await session.commit()
    return {"msg": "success", "publish_status": publish_status}

async def reject_article_db(session: AsyncSession, article_db: GeneratedUserStories, reason: str, curr_editor_id: UUID):
    user_story_id = article_db.user_story_id
    try:
        publish_result = await session.execute(
            update(UserStories)
                .where(UserStories.id == user_story_id)
                .values(
                    publish_status=UserStoryPublishStatus.REJECTED,
                    rejection_reason=reason
                )
                .returning(UserStories.publish_status, UserStories.rejection_reason)
        )

        await _set_editor_id(
            session, article_db, curr_editor_id
        )
        
        publish_status = publish_result.first()
        if not publish_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail='No story found for this generated article'
            )
        
        await session.commit()
        return publish_status
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error while rejecting article: {str(e)}")
    

# Creator management
async def get_all_creators_db(
    session: AsyncSession,
    curr_editor_id: UUID,
    limit: int = 20, 
    offset: int = 0
):  
    published_articles_count = (
        select(func.count(GeneratedUserStories.id))
        .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
        .where(
            GeneratedUserStories.author_id == Authors.id,
            UserStories.publish_status == UserStoryPublishStatus.PUBLISHED
        )
        .correlate(Authors)
        .scalar_subquery()
        .label('published_count')
    )
    result = await session.execute(
        select(
            Users.id,
            Users.first_name,
            Users.last_name,
            Users.email,
            Users.username,
            Users.active,
            Authors.bio,
            get_creator_profile_image(),
            published_articles_count
        )
            .join(Authors, Users.id == Authors.id, isouter=True)
            .join(
                EditorCities,
                and_(
                    EditorCities.editor_id == curr_editor_id,
                    EditorCities.city_id == Authors.city_id,
                ),
            )
            .where(Users.role == UserRoles.CREATOR)
            .order_by(Users.added_on.desc())
            .limit(limit)
            .offset(offset)
    )
    creators = result.all()
    # print(creators)
    return creators

async def approve_or_reject_creator_db(session: AsyncSession,  curr_editor_id: UUID, creator_id: UUID, approve: bool):
    values = {"active": approve, "approved_by": curr_editor_id, "approved_at": datetime.now()+timedelta(hours=5, minutes=30)} if approve else {"active": False}
    result = await session.execute(
        update(Users)
            .where(Users.id == creator_id)
            .values(values)
            .returning(Users)
    )
    await session.commit()
    creator = result.scalars().first()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'no creator found for id {creator_id}')
    return creator

async def reset_creator_password_db(session: AsyncSession, creator_id: UUID, new_password: str):
    new_hashed_password = hash_password(new_password)
    
    await session.execute(
        update(Users)
            .where(Users.id == creator_id)
            .values(password=new_hashed_password)
    )
    await session.commit()
    
    return {"status": "success"}
    
async def get_creator_by_id(session: AsyncSession, creator_id: UUID):
    result = await session.execute(
        select(
            Users.id,
            Users.first_name,
            Users.last_name,
            Users.email,
            Users.username,
            Users.active,
            Authors.bio,
            get_creator_profile_image()
        )
            .join(Authors, Users.id == Authors.id, isouter=True)
            .where(Users.id == creator_id)
            .limit(1)
    )
    creator = result.first()
    print(f"Creator fetched at get_creator_by_id: {creator}")
    if not creator:
        return None
    
    result = await session.execute(
        select(func.count(GeneratedUserStories.id).label('published_count'))
            .join(UserStories, GeneratedUserStories.user_story_id == UserStories.id)
            .where(
                GeneratedUserStories.author_id == creator_id,
                UserStories.publish_status == UserStoryPublishStatus.PUBLISHED
            )
    )
    published_count = result.scalar_one_or_none() or 0
    
    # print(f"Creator fetched at get_creator_by_id: {creator.__dict__}")
    print(f"Published count: {published_count}")
    
    return CreatorItem(
        id=creator.id,
        first_name=creator.first_name,
        last_name=creator.last_name,
        email=creator.email,
        username=creator.username,
        active=creator.active,
        bio=creator.bio,
        creator_profile_image=creator[7],  # get_creator_profile_image() result
        published_count=published_count,
    )
    
from src.creators.service import generate_unique_username

async def add_creator_db(session: AsyncSession, curr_editor_id: UUID, payload: CreateCreatorSchema):
    unique_username = await generate_unique_username(session, payload.email)
    hashed_password = hash_password(payload.password)
    
    try:
        result = await session.execute(
            insert(Users)
                .values(
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                    email=payload.email,
                    username=unique_username,
                    role=UserRoles.CREATOR,
                    password=hashed_password,
                    active=payload.active,
                    approved_by=curr_editor_id if payload.active else None,
                    approved_at=datetime.now()+timedelta(hours=5, minutes=30) if payload.active else None
                )
                .returning(Users)
        )
        await session.commit()
        
        creator = result.first()[0]
        print(creator)
        
        return CreatorItem(
            id=creator.id,
            first_name=creator.first_name,
            last_name=creator.last_name,
            email=creator.email,
            username=creator.username,
            active=creator.active,
            # bio=creator.bio,
            # profile_image_url=creator[7],  # get_creator_profile_image() result
            # published_count=0,
        )
    except IntegrityError as e:
        print(f"Error while adding new creator ({payload.email}): {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A creator with this email already exists"
        )
        
from src.models import Categories


async def store_article_categories(
    session: AsyncSession,
    article_id: UUID,
    category_ids: list[UUID]
):
    unique_category_ids = list(dict.fromkeys(category_ids))

    await session.execute(
        delete(ArticleCategories)
            .where(ArticleCategories.article_id == article_id)
    )

    if not unique_category_ids:
        return

    await session.execute(
        insert(ArticleCategories)
            .values([
                {"article_id": article_id, "category_id": category_id}
                for category_id in unique_category_ids
            ])
            .on_conflict_do_nothing(
                index_elements=["article_id", "category_id"]
            )
    )


async def validate_categories(
    session: AsyncSession,
    category_ids: list[UUID]
):
    category_ids = set(category_ids)
    result = await session.execute(
        select(Categories.id)
            .where(Categories.id.in_(category_ids))
    )
    validated_category_ids = result.scalars().all()
    
    validated_category_ids_set = set(c_id for c_id in validated_category_ids)
    invalid = category_ids - validated_category_ids_set
    
    if invalid:
        print(f"Found invalid categories: {', '.join(invalid)}")
    return list(validated_category_ids_set)
    
    
async def get_city_by_id(session: AsyncSession, city_id: UUID):
    city_db = await session.get(Cities, city_id)
    if not city_db:
        return None
    return city_db.name
