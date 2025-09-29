from src.models import UserStories, UserStoryStatus, GeneratedUserStories, UserStoryPublishStatus
from src.editor.schemas import EditArticleSchema

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DatabaseError
from sqlalchemy import select, update, or_
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException, status
import traceback

async def get_articles_by_publish_status(session: AsyncSession, editor_status: str, curr_editor_id: str, limit: int = 10, offset: int = 0):
    try:
        res = await session.execute(select(GeneratedUserStories.id, GeneratedUserStories.title, GeneratedUserStories.snippet, GeneratedUserStories.full_text, GeneratedUserStories.created_at).join(UserStories, onclause=UserStories.id == GeneratedUserStories.user_story_id).filter(UserStories.publish_status == editor_status, UserStories.status == UserStoryStatus.SUBMITTED, or_(GeneratedUserStories.editor_id == None, GeneratedUserStories.editor_id == curr_editor_id)).order_by(UserStories.created_at.desc()).limit(limit).offset(offset))
        articles = res.all()
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

async def update_article_db(session: AsyncSession, article_id: str, payload: EditArticleSchema, curr_editor_id: str):
    values = payload.model_dump()
    stmt = update(GeneratedUserStories).where(GeneratedUserStories.id == article_id).values(values).returning(GeneratedUserStories)
    result = await session.execute(stmt)
    article_db = result.scalars().first()
    if not article_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'no article found for id {article_id}')
    publish_status = await set_publish_status(session, article_db.user_story_id, UserStoryPublishStatus.PUBLISHED)
    await session.commit()
    return {'msg': "success", 'article_id': article_id, 'publish_status': publish_status}


async def set_publish_status(session: AsyncSession, user_story_id: str, new_publish_status: str):
    stmt = update(UserStories).where(UserStories.id == user_story_id).values({"publish_status": new_publish_status}).returning(UserStories.publish_status)
    result = await session.execute(stmt)
    publish_status = result.scalar_one_or_none()
    if not publish_status:
        return None
    return publish_status

async def set_editor_id(session: AsyncSession, article: GeneratedUserStories, editor_id: str):
    if not article.editor_id:
        await session.execute(update(GeneratedUserStories).values(editor_id=editor_id).where(GeneratedUserStories.id == article.id))
        return True
    return False

async def publish_article_db(session: AsyncSession, article_db: GeneratedUserStories, curr_editor_id: str):
    publish_status = await set_publish_status(session, article_db.user_story_id, UserStoryPublishStatus.PUBLISHED)
    if not publish_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no story found for this generated article')
    await session.commit()
    return {"msg": "success", "publish_status": publish_status}

async def reject_article_db(session: AsyncSession, article_db: GeneratedUserStories, reason: str, curr_editor_id: str):
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
    




