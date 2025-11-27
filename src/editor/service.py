from src.models import UserStories, UserStoryStatus, GeneratedUserStories, UserStoryPublishStatus, Users, UserRoles, Authors
from src.editor.schemas import EditArticleSchema
from src.utils.query import get_article_images_json_query, get_profile_image_expression, get_creator_profile_image
from src.creators.utils import hash_password
from src.editor.schemas import CreatorItem, CreateCreatorSchema

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy import select, update, or_, func, literal, case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from fastapi import HTTPException, status
import traceback
from uuid import UUID
from datetime import datetime, timedelta


Creators = aliased(Users)
Editors = aliased(Users)

async def get_articles_by_publish_status(session: AsyncSession, editor_status: str, curr_editor_id: UUID, limit: int = 10, offset: int = 0):
    try:
        # creator_profile_image = case(
        #     (Users.profile_image_key != None,
        #     func.concat(
        #         literal(get_bucket_base_url()),
        #         Users.profile_image_key
        #     )),
        #     else_=None
        # ).label("creator_profile_image")
        res = await session.execute(
                select(
                    GeneratedUserStories.id,
                    GeneratedUserStories.title,
                    # GeneratedUserStories.snippet,
                    # GeneratedUserStories.full_text,
                    GeneratedUserStories.category,
                    # GeneratedUserStories.tags,
                    # GeneratedUserStories.images_keys,
                    GeneratedUserStories.created_at,
                    UserStories.publish_status,
                    GeneratedUserStories.updated_at,
                    GeneratedUserStories.published_at,
                    # get_article_images_json_query(),
                    Creators.username.label('creator_username'),
                    Creators.first_name.label('creator_first_name'),
                    Creators.last_name.label('creator_last_name'),
                    Editors.first_name.label('editor_first_name'),
                    Editors.last_name.label('editor_last_name'),
                    Editors.username.label('editor_username')
                    # get_profile_image_expression(label_name="creator_profile_image")
                )
                    .join(UserStories, UserStories.id == GeneratedUserStories.user_story_id)
                    .join(Creators, Creators.id == GeneratedUserStories.author_id)
                    .join(Editors, Editors.id == GeneratedUserStories.editor_id, isouter=True)
                    .filter(
                        UserStories.publish_status == editor_status,
                        UserStories.status == UserStoryStatus.SUBMITTED,
                        # or_(
                        #     GeneratedUserStories.editor_id == None,
                        #     GeneratedUserStories.editor_id == curr_editor_id
                        # )
                    )
                    .order_by(UserStories.created_at.desc())
                    .limit(limit)
                    .offset(offset)
            )
        articles = res.all()
        # print([article._asdict() for article in articles])
        if not articles:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'no {editor_status} articles found')
        return articles
    except DatabaseError as e:
        msg = f'Error while {editor_status} fetching articles'
        print(msg)
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={
            "msg": msg,
            "error": str(e)
        })
    
async def get_article_by_id_db(session: AsyncSession, article_id: str):
    result = await session.execute(select(GeneratedUserStories).filter(GeneratedUserStories.id == article_id).limit(1))
    article = result.scalars().first()
    if not article:
        return None
    return article

async def edit_article_db(session: AsyncSession, article: GeneratedUserStories, payload: EditArticleSchema, curr_editor_id: UUID):
    article_id = article.id
    values = payload.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="all fields cannot be empty"
        )
        
    print(f"Editing article: {values}")
        
    result = await session.execute(
        update(GeneratedUserStories)
            .where(GeneratedUserStories.id == article_id)
            .values(editor_id=curr_editor_id, **values)
            .returning(GeneratedUserStories)
    )
    article_updated = result.scalars().first()
    
    await set_publish_status(
        session, article.user_story_id, UserStoryPublishStatus.WORK_IN_PROGRESS
    )
    await session.commit()
    
    return article_updated
    
    # stmt = update(GeneratedUserStories).where(GeneratedUserStories.id == article_id).values(values).returning(GeneratedUserStories)
    # result = await session.execute(stmt)
    # article_db = result.scalars().first()
    # if not article_db:
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'no article found for id {article_id}')
    # publish_status = await set_publish_status(session, article_db.user_story_id, UserStoryPublishStatus.PUBLISHED)
    # await session.commit()
    # return {'msg': "success", 'article_id': article_id, 'publish_status': publish_status}


async def set_publish_status(session: AsyncSession, user_story_id: UUID, new_publish_status: str):
    published_at = datetime.now()+timedelta(hours=5, minutes=30) if new_publish_status == UserStoryPublishStatus.PUBLISHED else None
    stmt = update(UserStories).where(UserStories.id == user_story_id).values({"publish_status": new_publish_status, "published_at": published_at}).returning(UserStories.publish_status)
    stmt = update(UserStories).where(UserStories.id == user_story_id).values({"publish_status": new_publish_status}).returning(UserStories.publish_status)
    result = await session.execute(stmt)
    publish_status = result.scalar_one_or_none()
    if not publish_status:
        return None
    return publish_status

async def _set_editor_id(session: AsyncSession, article: GeneratedUserStories, editor_id: str):
    if not article.editor_id:
        await session.execute(update(GeneratedUserStories).values(editor_id=editor_id).where(GeneratedUserStories.id == article.id))
        return True
    return False

async def publish_article_db(session: AsyncSession, article: GeneratedUserStories, curr_editor_id: UUID):
    publish_status = await set_publish_status(session, article.user_story_id, UserStoryPublishStatus.PUBLISHED)
    if not publish_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no story found for this generated article')
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
            .where(Users.role == UserRoles.CREATOR)
            .limit(limit)
            .offset(offset)
            .order_by(Users.added_on.desc())
    )
    creators = result.all()
    print(creators)
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