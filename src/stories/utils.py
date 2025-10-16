from datetime import datetime, timedelta
from typing import Optional, Annotated, Literal
from fastapi import Query, HTTPException
import re
import feedparser
import urllib.parse
import httpx
from datetime import datetime
from openai import AsyncOpenAI, OpenAIError
import json
import asyncio
import unicodedata

from src.config.settings import settings
from src.schemas import LocationDataSchema, GenerateOptionsSchema, ReqSchema
from src.models import UserStories

SCOPE_CONFIG = {
            'CITY': {'refresh_interval_mins': 60, 'max_days_back': 5},
            'STATE': {'refresh_interval_mins': 40, 'max_days_back': 3}, 
            'COUNTRY': {'refresh_interval_mins': 20, 'max_days_back': 2},
            'INTERNATIONAL': {'refresh_interval_mins': 15, 'max_days_back': 1}
        }

# def parse_story_date_to_datetime(story_pub_date: str) -> Optional[datetime]:
#     """
#     Convert story publication date string to datetime object.
#     Handles formats like: 40s, 30m, 2h, 3d, 1mo, 2yr
#     """
#     if not story_pub_date:
#         return None
    
#     story_pub_date = story_pub_date.strip()
#     match = re.match(r"(\d+)([a-zA-Z]+)", story_pub_date)
#     if not match:
#         return None
    
#     num = int(match.group(1))
#     unit = match.group(2)
    
#     now = datetime.now()
    
#     if unit == "s":
#         return now - timedelta(seconds=num)
#     elif unit == "m":
#         return now - timedelta(minutes=num)
#     elif unit == "h":
#         return now - timedelta(hours=num)
#     elif unit == "d":
#         return now - timedelta(days=num)
#     elif unit == "mo":
#         return now - timedelta(days=num * 30)  # Approximate
#     elif unit == "yr":
#         return now - timedelta(days=num * 365)  # Approximate
    
#     return None

RSS_FEEDS_SOURCES = [
    {
        "name": "Live Hindustan - Nagpur",
        "url": "https://api.livehindustan.com/feeds/rss/maharashtra/nagpur/rssfeed.xml",
        "category": "general"
    },
    {
        "name": "Times of India - Nagpur",
        "url": "https://timesofindia.indiatimes.com/rssfeeds/442002.cms",
        "category": "general"
    },
    {
        "name": "NagpurVocals Local News",
        "url": "https://www.nagpurvocals.com/rss/local",
        "category": "general"
    },
    {
        "name": "Indian Express - Nagpur",
        "url": "https://indianexpress.com/section/cities/nagpur/feed/",
        "category": "general"
    },
    {
        "name": "Lokmat Times - Nagpur",
        "url": "https://lokmat.news18.com/commonfeeds/v1/lok/rss/maharashtra/nagpur.xml",
        "category": "general"
    }
]

async def get_news(feed_source: dict):
    async with httpx.AsyncClient() as client:
        to_fetch = feed_source['url']
        response = await client.get(to_fetch)
        response.raise_for_status()

        feed = feedparser.parse(response.text)

        if response.status_code == 200:
            # return [ { "title": entry.get('title'), "summary": entry.get('summary', ''), "link": entry.get('link'), "published": entry.get('published') } for entry in feed.entries ]
            return {
                "feed": [ { "title": entry.get('title'), "summary": entry.get('summary', ''), "link": entry.get('link'), "published": entry.get('published') } for entry in feed.entries[:7] ],
                # "feed": feed.entries[:5],
                "source": feed_source['name'],
                "category": feed_source['category']
            }
        else:
            return {"error": "Failed to fetch feed"}
        

async def get_all_news():
    tasks = [get_news(source) for source in RSS_FEEDS_SOURCES]
    return await asyncio.gather(*tasks)

from datetime import datetime, timedelta
from typing import Optional
import re

from datetime import datetime, timedelta
from typing import Optional
import re

def parse_story_date_to_datetime(story_pub_date: str) -> Optional[datetime]:
    """
    Convert story publication date string to datetime object.
    Handles formats like: 40s, 30m, 2h, 3d, 1mo, 2yr
    Returns datetime with no microseconds.
    """
    if not story_pub_date:
        return None
    
    story_pub_date = story_pub_date.strip()
    match = re.match(r"(\d+)([a-zA-Z]+)", story_pub_date)
    if not match:
        return None
    
    num = int(match.group(1))
    unit = match.group(2)
    
    now = datetime.now()
    
    if unit == "s":
        dt = now - timedelta(seconds=num)
    elif unit == "m":
        dt = now - timedelta(minutes=num)
    elif unit == "h":
        dt = now - timedelta(hours=num)
    elif unit == "d":
        dt = now - timedelta(days=num)
    elif unit == "mo":
        dt = now - timedelta(days=num * 30)  # Approximate
    elif unit == "yr":
        dt = now - timedelta(days=num * 365)  # Approximate
    else:
        return None

    # Remove microseconds before returning
    return dt.replace(microsecond=0)



def needs_fetching(location_db):
    try:
        now = datetime.now()
        time_since_last_fetch = now - location_db.last_fetched_timestamp
        return time_since_last_fetch.total_seconds()/60 > location_db.refresh_interval_mins
    except Exception as e:
        print(e)
        return None

# def is_news_story_fresh(story, active_level: str, last_fetched_timestamp: Optional[datetime] = None) -> bool:
#     """
#     Determine if a news story is fresh based on:
#     1. If last_fetched_timestamp is None: use max_days_back logic
#     2. If last_fetched_timestamp exists: only include stories newer than that timestamp
#     """
#     story_pub_date = story.get("date", "").strip()
#     if not story_pub_date:
#         return False
    
#     story_datetime = parse_story_date_to_datetime(story_pub_date)
#     if not story_datetime:
#         return False
    
#     # If we have a last fetched timestamp, only get stories newer than that
#     if last_fetched_timestamp:
#         return story_datetime > last_fetched_timestamp
    
#     # Otherwise, use the max_days_back logic
#     max_days_back = max_days_back_map.get(active_level, 1)
#     cutoff_datetime = datetime.utcnow() - timedelta(days=max_days_back)
    
#     return story_datetime > cutoff_datetime

def is_news_story_fresh(story, cutoff_datetime: datetime) -> bool:
    """
    Determine if a news story is fresh based on the cutoff datetime.
    Only include stories newer than the cutoff timestamp.
    """
    story_pub_date = story.get("date", "")
    if not story_pub_date:
        return False, False
    
    story_pub_date = story_pub_date.replace(' ', '').strip()
    
    story_datetime = parse_story_date_to_datetime(story_pub_date)
    if not story_datetime:
        return False, False
    
    return story_datetime >= cutoff_datetime, story_datetime


# async def fetch_news_articles(request: LocationDataSchema, since_timestamp: datetime | None = None):
#     keyword = urllib.parse.quote(f"{request.query} news")
#     keep_fetching = True
#     base_url = f"https://serpapi.com/search?engine=bing_news&qft=sortbydate%3D%221%22&api_key={settings.EXHAUSTED_SERP_API_KEY}&q={keyword}"

#     page_size = 10
#     offset = 0
#     news_records = []

#     country_code = request.country_code
#     scope = request.scope

#     if country_code and scope == 'international':
#         api_url = f"{base_url}&cc={country_code}"
#     else:
#         api_url = base_url

#     fetch_news_after = since_timestamp if since_timestamp else SCOPE_CONFIG[scope]

#     async with httpx.AsyncClient() as client:
#         while keep_fetching:
#             response = await client.get(f"{api_url}&count={page_size}&first={offset}")
#             data = response.json()
#             results = data.get("organic_results", [])

#             if not results:
#                 break  # no more results

#             for story in results:
#                 if is_news_story_fresh(story, scope, last_fetched_timestamp):
#                     news_records.append(story)
#                 else:
#                     keep_fetching = False
#                     break

#             offset += page_size

#     return news_records

async def fetch_news_articles(request: LocationDataSchema, since_timestamp: datetime | None = None):
    keyword = urllib.parse.quote(f"{request.query} news")
    keep_fetching = True
    base_url = f"https://serpapi.com/search?engine=bing_news&qft=sortbydate%3D%221%22&api_key={settings.EXHAUSTED_SERP_API_KEY2}&q={keyword}&no_cache=true"

    page_size = 10
    offset = 0
    news_records = []
    seen_links = set()  # track unique links

    country_code = request.country_code
    scope = request.scope

    if (scope == 'CITY' or scope == 'STATE'):
        api_url = f"{base_url}&cc={country_code}"
    else:
        api_url = base_url

    # Calculate cutoff time based on scope if since_timestamp is None
    if since_timestamp is None:
        max_days_back = SCOPE_CONFIG[scope]['max_days_back']
        cutoff_datetime = datetime.now() - timedelta(days=max_days_back)
    else:
        cutoff_datetime = since_timestamp

    async with httpx.AsyncClient() as client:
        while keep_fetching:
            response = await client.get(f"{api_url}&count={page_size}&first={offset}")
            # print(f"{api_url}&count={page_size}&first={offset}")
            data = response.json()
            results = data.get("organic_results", [])
            if not results:
                break  # no more results

            for story in results:
                _ = is_news_story_fresh(story, cutoff_datetime)
                print(_)
                is_fresh, published_timestamp = _
                if is_fresh:
                    story['date'] = published_timestamp
                    link = story.get("link")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        news_records.append(story)
                else:
                    keep_fetching = False
                    break

            offset += page_size
    return news_records


openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

async def rewrite_story(options: GenerateOptionsSchema, story) -> dict:
    """
    Rewrite a story (title + snippet) using OpenAI API.
    Output: {"title": "...", "snippet": "..."} where snippet is HTML formatted.
    """

    if not story or not story.title or not story.snippet:
        return {"title": "", "snippet": ""}

    words = get_word_length_range(options.word_length)

    prompt = f"""
        You are an AI editorial assistant. Rewrite the following news article into a new version.

        Constraints:
        - Tone: {options.tone}
        - Style: {options.style}
        - Target length: around {words} words
        - Language: {options.language}
        - Output the rewritten snippet in clean HTML format, using proper <p>, <b>, <br> tags for readability.
        - Provide a new engaging title as well.

        Original Title: {story.title}
        Original Snippet: {story.snippet}

        Return ONLY valid JSON in this format:
        {{
        "title": "...",
        "snippet": "..."
        }}
            """

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional news editor."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        print("Rewrite error:", e)
        return None


async def get_prompt_response(request: ReqSchema) -> str:
    try:
        user_prompt = f"""
            Format requested: {request.format}

            Here are the details provided:
            - Who: {request.who}
            - What: {request.what}
            - When: {request.when}
            - Where: {request.where}
            - Why: {request.why}
            - How: {request.how}

            Write a professional {request.format} article based on the above information. 
            Follow proper journalistic structure and include a clear headline and well-organized body text.
            If any information seems incomplete, acknowledge it as 'details awaited' instead of making assumptions.
            """
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": request.sys_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

        content = response.choices[0].message.content
        return content

    except Exception as e:
        print("Rewrite error:", e)
        return None
    
import hashlib

def generate_hash(context: str) -> str:
    return hashlib.sha256(context.strip().lower().encode("utf-8")).hexdigest()


async def generate_ai_questions(user_story_db: UserStories) -> list[dict]:
    """Generate 5W1H+Sources questions in JSON format using GPT."""

    title = user_story_db.title
    context = user_story_db.context
    tone = user_story_db.tone
    style = user_story_db.style
    language = user_story_db.language
    word_length = user_story_db.word_length
    word_length_range = user_story_db.word_length_range

    PROMPT = f"""
        You are a journalism assistant helping to prepare inputs for generating a professional-grade news article.

        The user has provided the following information and preferences:

        Title (optional): {title or "N/A"}  
        Tone: {tone}  
        Style: {style}  
        Language: {language}  
        Word Count Target: {word_length} {word_length_range} words  
        Context/Brief Description: {context}

        Your task:
        Generate a concise set of clear, structured, and **fact-oriented questions** that will help gather specific, verifiable details needed to write a complete, accurate news article.

        Each question should focus on eliciting **concrete, descriptive, or measurable information** — not opinions or vague statements.

        ---

        ### Guidelines for the questions:

        - Generate **3 to 6** questions, depending on the complexity of the provided context.  
        - Questions must be **objective, direct, and fact-based**, allowing the user to answer with precise, verifiable details.  
        - Avoid **yes/no** questions.  
        - Avoid **subjective, interpretative, or speculative** phrasing unless the article’s style explicitly calls for it (e.g., if *Style = Opinion* or *Editorial*).  
        - Do **not** repeat information already clearly mentioned in the context.  
        - Aim to gather all essential details that would help an AI later write a balanced, factual, and complete news piece.  
        - Do **not** enforce a strict 5W1H format (who, what, when, where, why, how) — instead, focus on what information is most relevant to fill factual gaps.  
        - Examples of good questions:
        ✓ "When and where did the incident take place?"  
        ✓ "Who were the key officials or organizations involved?"  
        ✓ "What official statements or data have been released?"  
        ✓ "What were the main outcomes or developments following the event?"  
        - Examples of questions to avoid:
        × "Do you think the event was successful?"  
        × "How do people feel about this policy?"  
        × "Why did this happen?" (too speculative)

        ---

        ### Output Format Rules:

        Return the output **only** in valid JSON format — no explanations, notes, or extra text.

        Each question object must include:
        - `"question_key"` — string key such as "q1", "q2", etc.  
        - `"question_text"` — the full text of the question  

        ---

        ### Final Output Format:

        {{
        "questions": [
            {{ "question_key": "q1", "question_text": "..." }},
            {{ "question_key": "q2", "question_text": "..." }},
            ...
        ]
        }}
        """


    
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You generate structured questions for news writing."},
                {"role": "user", "content": PROMPT}
            ]
        )
        raw_output = response.choices[0].message.content

        data = json.loads(raw_output)
        return data.get("questions", [])
    except json.JSONDecodeError:
        return []
    
async def generate_user_story(user_story: UserStories, qna: list[dict]) -> dict:
    existing_title = user_story.title
    # del qna['question_id']
    # del qna['answer_id']
    # del qna['question_type']
    PROMPT = f"""
        You are an AI news writing assistant. Generate a professional-grade news article based on the following inputs:

        Options:
        - Tone: {user_story.tone or "casual"}  (e.g., formal, casual, neutral)
        - Style: {user_story.style or "informative"}  (e.g., informative, narrative, breaking news)
        - Language: {user_story.language or "English"}
        - Word Count Target: {f"{user_story.word_length} {str(user_story.word_length_range)}" if user_story.word_length else "short (300-500)"}  

        Story Context:
        "{user_story.context or ""}"  

        Optional Title (if provided):
        "{existing_title or ""}"  

        Questions and Answers:
        {qna}

        ---

        Output the result strictly in valid JSON format with the following keys (no explanations, no extra text):

        {{
        "title": "If 'Optional Title' above is empty, generate a suitable title here. Otherwise, return an empty string.",
        "english_title": "If the article is not in English, provide an exact translation (not summarization) of the original title into English, keeping it under 12 words. If the article is in English, leave this empty.",
        "snippet": "A 2–3 sentence HTML formatted summary (use <p>, <b>, <br> where appropriate)",
        "full_text": "The complete article text in HTML format with proper paragraphing, headings (<h2>, <h3>) if needed, and emphasis tags where useful.",
            "category": ["A list of 1–3 categories from this fixed list: [local-news, india, world, politics, sports, entertainment, crime, business, civic-issues, technology, environment, culture, general]. Should always be a list even i f there is only one category. Only include multiple categories if they truly fit the article. If none apply, use 'general'."],
        "tags": ["A list of 5–10 relevant keywords or short phrases based on the article (no hashtags, plain text)"]
        }}

        Rules:
        - Category must be strictly chosen from the provided list (or 'general' if none apply).
        - Make sure that the title is not too long or too short (max 100 characters).
        - The word count target is only for the full text field. Title and snippet are not counted.
        - Tags should reflect important entities, locations, people, issues, or topics mentioned in the article.
        - At least 70% of the tags MUST be in English, regardless of article language.
        - For non-English names/places, provide both original and English transliteration in tags.
        - Ensure journalistic clarity, avoid repetition, and follow the given tone, style, and word length.
    """

    try:
        # print(PROMPT)
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",  # or your preferred model
            messages=[
                {"role": "system", "content": "You are a professional AI news article writer."},
                {"role": "user", "content": PROMPT}
            ],
            temperature=0.5
        )

        raw_content = response.choices[0].message.content.strip()
        # print(raw_content)

        # Try parsing JSON output from the model
        try:
            article = json.loads(raw_content)
            # article['category'] = article.get('category', '').strip().lower().replace(' ', '-')
            article['category'] = [category.lower().replace(' ', '-') for category in article['category']]
        except json.JSONDecodeError:
            print("AI returned invalid JSON. Wrapping in fallback format.")
            # article = {
            #     "title": "",
            #     "snippet": "<p>Summary not available</p>",
            #     "full_text": f"<p>{raw_content}</p>"
            # }
            return None
        if existing_title:
            article['title'] = existing_title
        return article

    except Exception as e:
        print(f"Error generating user story: {e}")
        # return {
        #     "title": "",
        #     "snippet": "<p>Error occurred while generating the story.</p>",
        #     "full_text": ""
        # }
        return None

def get_word_length_range(length_option: str):
    LENGTH_RANGES = {
        'short': (300, 500),
        'medium': (500, 800),
        'long': (800, 1200)
    }
    return LENGTH_RANGES.get(length_option, (300, 500))


def get_story_status_dep(
    status: Annotated[str, Query(description="Story status filter")] = 'draft'
) -> Literal['draft', 'submitted', 'rejected', 'published']:
    """Convert status to lowercase and validate."""
    status_lower = status.lower().strip()
    valid_statuses = ['draft', 'submitted', 'rejected', 'published']
    
    if status_lower not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    return status_lower


def sluggify(title: str, max_words: int = 6) -> str:
    """
    Convert a title to a URL-friendly slug, using the first n words.
    
    Args:
        title: The text to convert
        max_words: Maximum number of words to include in the slug (default 6)
    
    Returns:
        A URL-safe slug using first n words
    """
    # Normalize unicode (decompose accented characters)
    text = unicodedata.normalize('NFKD', title)
    
    # Convert to lowercase and get first n words
    words = text.lower().split()[:max_words]
    text = ' '.join(words)
    
    # Replace common special characters and spaces with hyphens
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE)
    text = re.sub(r'[-\s]+', '-', text)
    
    # Trim hyphens
    return text.strip('-')