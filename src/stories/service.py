from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, update, select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
import asyncio
import httpx
import traceback
from openai import OpenAIError
from fastapi import Path, HTTPException, Depends, status
from typing import Annotated
from uuid import UUID

from src.models import Locations, StoriesRaw, UserStories, UserStoriesQuestions, UserStoriesAnswers, UserStoryStatus, UserStoryPublishStatus, GeneratedUserStories, Users
from src.config.database import get_session
from src.schemas import LocationDataSchema, AnswerSchema, CreateStorySchema, UserStoryFullResponseSchema, EditGeneratedArticleSchema
from src.stories.utils import SCOPE_CONFIG, generate_hash, get_word_length_range, generate_ai_questions,generate_user_story, sluggify
from src.auth.dependencies import role_checker
from src.aws.utils import get_full_s3_object_url
from src.utils.query import get_article_images_json_query, creator_profile_image, editor_profile_image

refresh_interval_map = {"city": 60, "state": 40, "country": 30, "world": 15}

async def get_levels_to_fetch(session: AsyncSession, location: LocationDataSchema):
    query = select(Locations).filter(
        or_(
            and_(
                Locations.city == location.city,
                Locations.state == location.state,
                Locations.country == location.country,
                Locations.level == 'city'
            ),
            and_(
                Locations.state == location.state,
                Locations.country == location.country,
                Locations.level == 'state'
            ),
            and_(
                Locations.country == location.country,
                Locations.level == 'country'
            ),
            Locations.level == 'world'
        )
    )
    results = await session.execute(query)
    locations_db = results.scalars().all()
    locations_by_level = {loc.level: loc for loc in locations_db}

    locations_to_fetch = []

    for lev in ["city", "state", "country", "world"]:
        if lev in locations_by_level:
            loc = locations_by_level[lev]
            if not await is_location_fresh(loc):
                locations_to_fetch.append({
                    "location": loc,
                    "level": lev,
                    "exists": True
                })
        else:
            location_mapping = {
                "city": {
                    "city": location.city,
                    "state": location.state,
                    "country": location.country
                },
                "state": {
                    "state": location.state,
                    "country": location.country
                },
                "country": {
                    "country": location.country
                },
                "world": "world"
            }
            
            locations_to_fetch.append({
                "level": lev,
                "exists": False,
                "location": location_mapping[lev]
            })

    return locations_to_fetch

    
async def is_location_fresh(location: Locations):
    now = datetime.now()
    # return now - datetime.strptime(location.last_fetched_timestamp, "%Y-%m-%d %H:%M:%S") < timedelta(minutes=location.refresh_interval_mins)
    return now - location.last_fetched_timestamp < timedelta(minutes=location.refresh_interval_mins)


async def fetch_for_locations(session: AsyncSession, locations_to_fetch: list[dict]):
    # create location records
    # locations_to_add = [loc for loc in locations_to_fetch if not loc['exists']]
    locations_to_add = []
    locations_to_refetch = []
    for loc in locations_to_fetch:
        if loc['exists']:
            locations_to_refetch.append(loc['location'])
        else:
            locations_to_add.append(loc)

    added_locations_db = await store_location_records(session, locations_to_add)

    # add the already existing location objects
    added_locations_db.extend(locations_to_refetch)
    fetch_tasks = [fetch_and_store_news_stories(loc) for loc in added_locations_db]
    res = await asyncio.gather(*fetch_tasks)





    

async def store_location_records(session: AsyncSession, locations_to_add: list[dict]):
    
    max_days_back_map = {"city": 4, "state": 3, "country": 2, "world": 1}

    locations_to_add = [ {"city": loc['location'].get('city'), "state": loc['location'].get('state'), "country": loc['location'].get('country'), "level": loc['level'], "refresh_interval_mins": refresh_interval_map.get(loc['level']), "max_days_back": max_days_back_map.get(loc['level'])} for loc in locations_to_add ]

    query = insert(Locations).values(locations_to_add).returning(Locations.id, Locations.level, Locations.city, Locations.state, Locations.country, Locations.max_days_back, Locations.refresh_interval_mins)
    try:
        result = await session.execute(query)
        await session.commit()
    except DatabaseError as e:
        await session.rollback()
        print(f"Error occurred while storing location records: {e}")

    return result.scalars().all() or locations_to_add


# async def fetch_and_store_news_stories(location: Locations):
#     async with httpx.AsyncClient() as client:
#         response = await client.get(f"https://serpapi.com/search?engine=bing_news&cc={location.country_code}&qft=%22sortbydate%3D%221%22%22")

def parse_bing_date(date_str: str) -> datetime:
    """Convert Bing's date string (e.g. '4d', '2h', '30m') into an absolute datetime."""
    now = datetime.now(timezone.utc)
    if date_str.endswith("d"):
        return now - timedelta(days=int(date_str[:-1]))
    elif date_str.endswith("h"):
        return now - timedelta(hours=int(date_str[:-1]))
    elif date_str.endswith("m"):
        return now - timedelta(minutes=int(date_str[:-1]))
    return now  # fallback if unknown format

async def fetch_and_store_news_stories(location):
    news_records = []
    now = datetime.now(timezone.utc)

    page_size = 10   # number of results per page
    offset = 0       # pagination offset
    keep_fetching = True

    async with httpx.AsyncClient() as client:
        while keep_fetching:
            response = await client.get(
                "https://serpapi.com/search",
                params={
                    "engine": "bing_news",
                    "cc": location.country_code,
                    "qft": '"sortbydate="1""',
                    "count": page_size,
                    "first": offset,
                },
            )
            data = response.json()
            results = data.get("organic_results", [])

            if not results:
                break  # no more results

            for story in results:
                story_time = parse_bing_date(story.get("date", "0d"))

                if location.last_fetched_timestamp is None:
                    # Initial fetch: stop when stories are older than max_days_back
                    if story_time >= now - timedelta(days=location.max_days_back):
                        news_records.append(story)
                    else:
                        keep_fetching = False
                        break
                else:
                    # Refresh fetch: only include stories newer than last fetch but within refresh interval
                    refresh_cutoff = location.last_fetched_timestamp + timedelta(
                        minutes=location.refresh_interval_mins
                    )
                    if location.last_fetched_timestamp < story_time <= refresh_cutoff:
                        news_records.append(story)
                    elif story_time <= location.last_fetched_timestamp:
                        keep_fetching = False
                        break

            offset += page_size  # move to next page

    return news_records

async def get_location_status(session: AsyncSession, request: LocationDataSchema):
    try:
        columns = (Locations.id, Locations.last_fetched_timestamp, Locations.refresh_interval_mins, Locations.max_days_back)
        scope = request.scope
        if scope == 'INTERNATIONAL':
            query = select(*columns).filter(Locations.level == 'INTERNATIONAL')
        else:
            location = request.location
            where_condition = {
                'CITY': (Locations.city == location.city, Locations.state == location.state, Locations.country_code == request.country_code, Locations.level == request.scope),
                'STATE': (Locations.city.is_(None) , Locations.state == location.state, Locations.country_code == request.country_code, Locations.level == request.scope),
                'COUNTRY': (Locations.city.is_(None), Locations.state.is_(None), Locations.country_code == request.country_code, Locations.level == request.scope)
            }
            query = select(*columns).filter(*where_condition.get(scope))
        result = await session.execute(query)
        return result.first()
    except Exception as e:
        print(e)
        traceback.print_exc()
        return None

def prepare_db_object(location: LocationDataSchema):
    now = datetime.now()
    scope = location.scope
    if scope == 'city':
        return {
            'city': location.query,
            'state': '',
            'country': '',
            'country_code': location.country,
            'level': scope,
            'last_fetched_timestamp': now,
            'refresh_interval_mins': refresh_interval_map.get(scope)
        }
    elif scope == 'state':
        return {
            'city': '',
            'state': location.query,
            'country': '',
            'country_code': location.country,
            'level': scope,
            'last_fetched_timestamp': now,
            'refresh_interval_mins': refresh_interval_map.get(scope)
        }
    elif scope == 'country':
        return {
            'city': '',
            'state': '',
            'country': location.query,
            'country_code': location.country,
            'level': scope,
            'last_fetched_timestamp': now,
            'refresh_interval_mins': refresh_interval_map.get(scope)
        }
    else:
        return {
            'city': '',
            'state': '',
            'country': '',
            'country_code': '',
            'level': scope,
            'last_fetched_timestamp': now,
            'refresh_interval_mins': refresh_interval_map.get(scope)
        }    

# async def update_or_add_location_record(session: AsyncSession, location: LocationDataSchema, exists: bool):
#     if not exists:
#         location_db_obj = prepare_db_object(location)
#         query = insert(Locations).values(location_db_obj)
#     else:
#         query = update(Locations).where(
#             and_(
#                 getattr(Locations, location.scope) == location.query,
#                 Locations.country_code == location.country,
#                 Locations.level == location.scope
#             )
#         ).values(
#             last_fetched_timestamp=datetime.now()
#         )

#     try:
#         result = await session.execute(query)
#         await session.commit()
#         return result.lastrowid
#     except DatabaseError as e:
#         print(f"Error while storing location {location.query}: {e}")
#         return None

async def add_location_record(session: AsyncSession, request: LocationDataSchema):
    try:
        current_timestamp = datetime.now()
        config = SCOPE_CONFIG.get(request.scope)

        new_location = Locations(
            city=request.location.city if request.location else None,
            state=request.location.state if request.location else None,
            country=request.location.country if request.location else None,
            country_code=request.country_code,
            level=request.scope,
            last_fetched_timestamp=current_timestamp,
            refresh_interval_mins=config['refresh_interval_mins'],
            max_days_back=config['max_days_back']
        )
        session.add(new_location)
        await session.commit()
        await session.refresh(new_location)
        return new_location
    except Exception as e:
        await session.rollback()
        print(f"Error adding location record: {str(e)}")
        return None
    
async def update_location_timestamp(session: AsyncSession, location_id: str):
    try:
        stmt = update(Locations).where(Locations.id == location_id).values({"last_fetched_timestamp": datetime.now()}).execution_options(synchronize_session=False)
        result = await session.execute(stmt)
        await session.commit()
        if not result.rowcount:
            return False
        return True
    except Exception as e:
        print(f"Error updating location timestamp for {location_id}: {str(e)}")
        traceback.print_exc()
        return True

async def add_stories_to_db(session: AsyncSession, news_records: list[dict], location_id: str):
    if not news_records:
        return []

    stories_to_insert = []
    for article in news_records:
        story_data = {
            "title": article.get("title"),
            "snippet": article.get("snippet"),
            "link": article.get("link"),
            "source": article.get("source"),
            "published_timestamp": article.get("date"),
            "thumbnail": article.get("thumbnail"),
            "location_id": location_id,
        }
        stories_to_insert.append(story_data)

    try:
        stmt = (
            insert(StoriesRaw)
            .values(stories_to_insert)   # ✅ pass list here, not into execute()
            .returning(
                StoriesRaw.id,
                StoriesRaw.title,
                StoriesRaw.snippet,
                StoriesRaw.link,
                StoriesRaw.source,
                StoriesRaw.published_timestamp,
                StoriesRaw.thumbnail,
                StoriesRaw.location_id,
            )
        )

        result = await session.execute(stmt)
        rows: list[Row] = result.fetchall()

        await session.commit()

        # Sort by timestamp DESC
        sorted_rows = sorted(
            rows,
            key=lambda r: r.published_timestamp or "",
            reverse=True
        )

        # Convert to plain dicts for JSON response
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "snippet": r.snippet,
                "link": r.link,
                "source": r.source,
                "date": str(r.published_timestamp),
                "thumbnail": r.thumbnail
            }
            for r in sorted_rows
        ]

    except Exception as e:
        await session.rollback()
        print(f"Error in batch insert: {str(e)}")
        return None



    
# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import AsyncSession
# from datetime import datetime, timedelta

async def fetch_stories_from_db(session: AsyncSession, location_id: str):
    try:
        result = await session.execute(select(Locations.max_days_back).filter(Locations.id == location_id))
        max_days_back = result.scalar_one_or_none()

        cutoff_datetime = datetime.now() - timedelta(days=max_days_back+1 if max_days_back is not None else 2)

        stmt = (
            select(StoriesRaw)
            .join(Locations)
            .where(Locations.id == location_id)
            .where(StoriesRaw.published_timestamp >= cutoff_datetime)
            .order_by(StoriesRaw.published_timestamp.desc())
        )

        result = await session.execute(stmt)
        stories = result.scalars().all()
        
        return [{
            "id": story.id,
            "title": story.title, 
            "snippet": story.snippet, 
            "link": story.link, 
            "source": story.source, 
            "date": str(story.published_timestamp.replace(microsecond=0)), 
            "thumbnail": story.thumbnail
        } for story in stories]

    except Exception as e:
        print(e)
        traceback.print_exc()
        return []

        
async def get_story_by_id(session: AsyncSession, story_id: str):
    try:
        result = await session.execute(select(StoriesRaw.id, StoriesRaw.title, StoriesRaw.snippet, StoriesRaw.link).filter(StoriesRaw.id == story_id))
        return result.first()
    except Exception as e:
        print(e)
        return None
    

# User stories functions:
async def create_user_story_db(session: AsyncSession, request: CreateStorySchema, curr_creator_id: str):
    try:
        # Normalize and hash inputs
        context = request.context.strip()
        title = request.title.strip() if request.title else None
        hashed_context = generate_hash(context)
        hashed_title = generate_hash(title) if title else None

        # Extract writing options
        options = request.options
        word_length_range = get_word_length_range(options.word_length)

        # Create story ORM object
        new_story = UserStories(
            title=title,
            title_hash=hashed_title,
            context=context,
            context_hash=hashed_context,
            tone=options.tone,
            style=options.style,
            language=options.language,
            word_length=options.word_length,
            word_length_range=str(word_length_range),
            author_id=curr_creator_id
        )

        session.add(new_story)
        await session.commit()
        await session.refresh(new_story)

        return {
            "id": new_story.id,
            "status": new_story.status,
            "title": new_story.title,
            "context": new_story.context,
            "tone": new_story.tone,
            "style": new_story.style,
            "language": new_story.language,
            "word_length": new_story.word_length,
            "word_length_range": new_story.word_length_range,
        }

    except IntegrityError:
        await session.rollback()
        traceback.print_exc()
        raise HTTPException(
            status_code=409,
            detail="A story with the same context or title already exists.",
        )
    except Exception as e:
        await session.rollback()
        print("Error while creating new story")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating the story.",
        )
    
async def get_user_story_by_id(session: AsyncSession, user_story_id: str):
    try:
        # print(user_story_id)
        result = await session.execute(select(UserStories).filter(UserStories.id == user_story_id))
        return result.scalars().first()
    except Exception as e:
        print(e)
        return None
    
async def get_user_story_or_404(session: Annotated[AsyncSession, Depends(get_session)], curr_creator: Annotated[Users, Depends(role_checker('creator'))], user_story_id: str = Path(...)):
    user_story = await get_user_story_by_id(session, user_story_id)
    if not user_story:
        raise HTTPException(status_code=404, detail="story not found")
    if user_story.author_id != curr_creator.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"story {user_story.id} does not belong to the creator {curr_creator.id}"
        ) 

    return user_story
    
async def get_user_story_questions_db(session: AsyncSession, user_story_id: str):
    result = await session.execute(select(UserStoriesQuestions).filter(UserStoriesQuestions.user_story_id == user_story_id, UserStoriesQuestions.is_active == True))
    return result.scalars().all()

async def deactivate_old_questions(session: AsyncSession, user_story_id: str):
    stmt = update(UserStoriesQuestions).where(UserStoriesQuestions.user_story_id == user_story_id).values(is_active=False)
    await session.execute(stmt)
    await session.commit()

async def generate_and_store_story_questions(session: AsyncSession, user_story_id: str, force_regenerate: bool = False):
    user_story = await get_user_story_by_id(session, user_story_id)
    if not user_story:
        raise HTTPException(status_code=404, detail="User story not found")

    existing_questions = await get_user_story_questions_db(session, user_story_id)

    if existing_questions and not force_regenerate:
        return existing_questions

    try:
        questions = await generate_ai_questions(user_story)
        if not questions:
            raise HTTPException(status_code=500, detail="Error while parsing questions or no questions returned")
    except OpenAIError as e:
        print(str(e))
        raise HTTPException(status_code=502, detail="openai service error")    
    
    try:
        await deactivate_old_questions(session, user_story_id)
        stored_questions = await store_questions(session, user_story_id, questions)
        return stored_questions
    except Exception as e:
        return HTTPException(status_code=500, detail=f"DB error: {str(e)}")
    

async def store_questions(session: AsyncSession, user_story_id: str, questions: list[dict]):
    questions_to_insert = [{**question, "user_story_id": user_story_id} for question in questions]

    try:
        stmt = insert(UserStoriesQuestions).values(questions_to_insert).returning(UserStoriesQuestions)
        result = await session.execute(stmt)
        await session.commit()
        return result.scalars().all()
    except Exception as e:
        print(F"Error storing questions: {str(e)}")
        await session.rollback()
        traceback.print_exc()
        return None
    
async def upsert_answer(session: AsyncSession, user_story_id: str, answer: AnswerSchema):
    try:
        # Ensure the question belongs to this user story
        r = await session.execute(
            select(UserStoriesQuestions.id).filter(
                UserStoriesQuestions.id == answer.question_id,
                UserStoriesQuestions.user_story_id == user_story_id
            )
        )
        question_id = r.scalar_one_or_none()
        if not question_id:
            raise HTTPException(status_code=404, detail="Question not found for this user story")

        stmt = (
            insert(UserStoriesAnswers)
            .values(
                user_story_id=user_story_id,
                question_id=question_id,
                answer_text=answer.answer_text,
                updated_at=func.now()
            )
            .on_conflict_do_update(
                index_elements=["user_story_id", "question_id"],
                set_={
                    "answer_text": answer.answer_text,
                    "updated_at": func.now(),
                },
            )
            .returning(UserStoriesAnswers.id)
        )

        result = await session.execute(stmt)
        await session.commit()

        return {"status": "success", "answer_id": result.scalar_one_or_none()}

    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Invalid data or constraint violation")
    
    
async def get_qna_by_user_story_id(session: AsyncSession, user_story_id: str, isouter: bool = False):
    result = await session.execute(select(UserStoriesQuestions.id.label('question_id'), UserStoriesQuestions.question_type, UserStoriesQuestions.question_text.label('question'), UserStoriesAnswers.id.label('answer_id'), UserStoriesAnswers.answer_text.label('answer')).join(
        UserStoriesAnswers, UserStoriesQuestions.id == UserStoriesAnswers.question_id,
        isouter=isouter
    ).filter(
        UserStoriesQuestions.user_story_id == user_story_id,
        UserStoriesQuestions.is_active == True
    ))
    qna = result.mappings().all()
    if qna:
        return [dict(row) for row in qna]
    return []

async def get_generated_story_db(session: AsyncSession, user_story_id: str):
    query = select(GeneratedUserStories.id,
                    GeneratedUserStories.title,
                    GeneratedUserStories.snippet,
                    GeneratedUserStories.full_text,
                    GeneratedUserStories.created_at,
                    GeneratedUserStories.updated_at,
                    GeneratedUserStories.category,
                    GeneratedUserStories.tags,
                    GeneratedUserStories.slug,
                    get_article_images_json_query()).filter(GeneratedUserStories.user_story_id == user_story_id)
    result = await session.execute(query)
    return result.first() or None

async def get_complete_story_by_id(session: AsyncSession, user_story_id: str, curr_creator_id: str):
    try:
        user_story_db = await get_user_story_by_id(session, user_story_id)
        if not user_story_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'User story with {user_story_id} not found')
        
        if user_story_db.author_id != curr_creator_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
            )
        
        qna = await get_qna_by_user_story_id(session, user_story_db.id, isouter=True)
        # print(qna)
        print(user_story_db.__dict__)
        if user_story_db.status == UserStoryStatus.COLLECTING:
            return UserStoryFullResponseSchema(user_story=user_story_db, qna=qna)
        
        generated_article_db = await get_generated_story_db(session, user_story_id)

        return UserStoryFullResponseSchema(user_story=user_story_db, qna=qna, generated=generated_article_db)
    except DatabaseError as dbe:
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(dbe))
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


import secrets

async def generate_unique_slug(session: AsyncSession, title: str, max_attempts: int = 5):
    title_slug = sluggify(title)
    slug = title_slug
    for _ in range(max_attempts):
        suffix = secrets.token_hex(3)
        slug = f"{title_slug}-{suffix}"
        existing = await session.execute(
            select(GeneratedUserStories).where(GeneratedUserStories.slug == slug)
        )
        if not existing.scalar_one_or_none():
            return slug

async def store_generated_article(session: AsyncSession, generated_user_story: dict, user_story_id: str, creator_id: str):
    title = generated_user_story.get('title')
    slug = await generate_unique_slug(session, title)

    print(generated_user_story)

    stmt = insert(GeneratedUserStories).values(user_story_id=user_story_id, author_id=creator_id, slug=slug, **generated_user_story).returning(
        GeneratedUserStories.id,
        GeneratedUserStories.user_story_id,
        GeneratedUserStories.author_id,
        GeneratedUserStories.slug,
        GeneratedUserStories.title,
        GeneratedUserStories.snippet,
        GeneratedUserStories.full_text,
        GeneratedUserStories.category,
        GeneratedUserStories.tags,
        GeneratedUserStories.created_at,
        get_article_images_json_query()  # include computed JSON in return
    )
    result = await session.execute(stmt)

    await session.execute(update(UserStories).where(UserStories.id == user_story_id).values({"status": UserStoryStatus.GENERATED}))
    await session.commit()
    return result.first()

async def get_generated_user_story(
    session: AsyncSession, user_story: UserStories, force_regenerate: bool = False
):
    user_story_id = user_story.id
    creator_id = user_story.author_id
    # Return cached/generated article if not regenerating
    existing_generated_story = await get_generated_story_db(session, user_story_id)
    if existing_generated_story and not force_regenerate:
        return existing_generated_story

    # Get QnA for story
    try:
        qna = await get_qna_by_user_story_id(session, user_story_id)
        if not qna:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No QnA found for this story",
            )
    except HTTPException:
        raise
    except TypeError as e:
        print("QnA parsing error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error parsing QnA DB object to dict",
        )
    except Exception as e:
        print("Unexpected error fetching QnA")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error while fetching questions and answers",
        )

    # Generate article
    generated_story_dict = await generate_user_story(user_story, [{"question": row.get('question ]'), "answer": row.get('answer')} for row in qna])
    if not generated_story_dict:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error while generating article or JSON parsing",
        )

    # Store in DB
    try:
        generated_story_db = await store_generated_article(
            session, generated_story_dict, user_story_id, creator_id
        )
        return generated_story_db
    except Exception as e:
        print("Error while storing generated article in DB")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error while storing generated article in DB",
        )

    # return {"msg": "hello"}

from src.schemas import UploadedImageKeys

async def update_user_story_status(session: AsyncSession, generated_article: GeneratedUserStories, request: UploadedImageKeys):
    try:
        if request:
            await session.execute(
                update(GeneratedUserStories)
                    .where(GeneratedUserStories.id == generated_article.id)
                    .values(images_keys=request.images_keys)
            )
        
        result = await session.execute(update(UserStories).where(UserStories.id == generated_article.user_story_id, UserStories.author_id == generated_article.author_id).values({'status': UserStoryStatus.SUBMITTED}).returning(UserStories.id, UserStories.status))
        await session.commit()
        user_story_db = result.first()
        return {"id": user_story_db.id, "status": user_story_db.status}
    except Exception as e:
        msg = f"Error while updating story status to submitted: {str(e)}"
        print(msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)
    
async def get_user_stories_db(session: AsyncSession, curr_creator_id: str, story_status: str, limit: int = 10, offset: int = 0):
    try:
        query = select(UserStories.id, UserStories.title, UserStories.context, UserStories.status, UserStories.publish_status, UserStories.created_at.label('initiated_at'), GeneratedUserStories.title.label('generated_title'), GeneratedUserStories.snippet.label('generated_snippet'), GeneratedUserStories.full_text.label('generated_story_full_text'), GeneratedUserStories.category, GeneratedUserStories.tags, get_article_images_json_query(), GeneratedUserStories.created_at.label('generated_at')).join(GeneratedUserStories, onclause=UserStories.id == GeneratedUserStories.user_story_id, isouter=True).filter(UserStories.author_id == curr_creator_id)

        if story_status == 'draft':
            query = query.filter(or_(UserStories.status == UserStoryStatus.COLLECTING, UserStories.status == UserStoryStatus.GENERATED))
        elif story_status == 'submitted':
            query = query.filter(and_(UserStories.status == UserStoryStatus.SUBMITTED, UserStories.publish_status == UserStoryPublishStatus.PENDING))
        elif story_status == 'rejected':
            query = query.filter(UserStories.publish_status == UserStoryPublishStatus.REJECTED)
        elif story_status == 'published':
            query = query.filter(UserStories.publish_status == UserStoryPublishStatus.PUBLISHED)

        query = query.limit(limit).offset(offset).order_by(UserStories.created_at.desc())

        result = await session.execute(query)
        return result.mappings().all()
    except DatabaseError as dbe:
        err_msg = f"Database error while fetching stories with status {story_status}: {str(dbe)}"
        print(err_msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err_msg)





async def edit_generated_article_db(session: AsyncSession, curr_creator_id: str, generated_article_id: str, updates: EditGeneratedArticleSchema):
    try:
        article_db = await session.get(GeneratedUserStories, generated_article_id)

        if not article_db:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail = f"no generated article found with id {generated_article_id}")
        
        if curr_creator_id != article_db.author_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Cannot edit other creator's articles"
            )
        
        if article_db.user_story.status not in [UserStoryStatus.COLLECTING, UserStoryStatus.GENERATED]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="cannot edit a submitted article"
            )

        updates_dict = updates.model_dump(exclude_none=True)
        if not updates_dict:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='all fields cannot be null')
        
        result = await session.execute(update(GeneratedUserStories).where(GeneratedUserStories.id == generated_article_id, GeneratedUserStories.author_id == curr_creator_id).values(**updates_dict).returning(GeneratedUserStories))
        await session.commit()
        
        edited_article = result.first()._asdict()
        images_keys = edited_article.get('images_keys', {})
        edited_article['images'] = [{"key": key, "url": get_full_s3_object_url(key)} for key in images_keys]
        edited_article.pop('images_keys', None)
        return edited_article
    
    except DatabaseError as e:
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error while updating article {generated_article_id} {str(e)}")