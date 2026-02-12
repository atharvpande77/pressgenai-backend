import openai
from src.config.settings import settings

client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

POLICE_HELPDESK_SYSTEM_PROMPT = """You are an official Nagpur City Police helpdesk assistant.

Answer only general informational queries asked under "Other Enquiry".
Do NOT handle emergencies, complaints, FIRs, legal accusations, or urgent situations.
If the message is urgent or a complaint, instruct the user to contact the nearest police station or dial 112.

Respond in the same language as the user (English or Marathi).
Keep replies clear, polite, and concise.
Do not speculate or give legal advice.
If information is unavailable, say so clearly."""


async def get_police_helpdesk_response(query: str, language: str = "English") -> str:
    """
    Calls OpenAI chat completions API to get a response for police helpdesk queries.
    
    Args:
        query: The user's question/message
        language: The language to respond in (English or Marathi)
    
    Returns:
        The assistant's response text
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"{POLICE_HELPDESK_SYSTEM_PROMPT}"
            },
            {
                "role": "user",
                "content": query
            }
        ],
        temperature=0.3,
        max_tokens=500
    )
    
    return response.choices[0].message.content

def inject_initial_context(thread_id: str, goal: str, client):
    goal_map = {
        "retirement": "Retirement planning",
        "child_education": "Child education planning",
        "savings": "Savings with protection",
        "human_life_value": "Human Life Value assessment"
    }

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=f"""
            The user has already selected the primary planning objective as:
            {goal_map.get(goal, goal)}.

            Do NOT ask the user to choose a planning goal again.
            Proceed with questions relevant to this objective only.
            """
    )


TABLE_NAME = "police_whatapp_bot_session_store"


async def check_if_message_after_ama(ddb, conversation_id: str, message: str) -> bool:
    """
    Tracks if "Ask me anything!" has been reached in a conversation.
    Also sets the language based on which trigger message was received.
    Returns True if conversation is past AMA state (should call GPT).
    Returns False if AMA not yet reached (should NOT call GPT).
    """
    table = await ddb.Table(TABLE_NAME)
    
    if message.lower() == "ask me anything!":
        await table.put_item(Item={
            "conversation_id": conversation_id,
            "ama_reached": True,
            "language": "English"
        })
        return False
    
    if message == "कोणतेही प्रश्न विचारा":
        await table.put_item(Item={
            "conversation_id": conversation_id,
            "ama_reached": True,
            "language": "Marathi"
        })
        return False
    
    # Check if ama_reached is True in DynamoDB
    response = await table.get_item(Key={"conversation_id": conversation_id})
    item = response.get("Item", {})
    return item.get("ama_reached", False)


async def get_conversation_by_id(ddb, conversation_id: str) -> dict:
    """Returns the conversation data from DynamoDB, defaults to empty dict."""
    table = await ddb.Table(TABLE_NAME)
    response = await table.get_item(Key={"conversation_id": conversation_id})
    return response.get("Item", {"language": "English"})


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def get_curr_location_jurisdiction_and_nearest_station(session: AsyncSession, lat: float, lon: float):
    """
    Get both containing and nearest police station.
    Simpler version with two separate queries.
    """
    # Query 1: Find containing station
    containing_result = await session.execute(
        text("""
            SELECT 
                id,
                name,
                address,
                lat,
                lon,
                pi_name,
                pi_phone,
                zone,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                 ) as distance_meters
            FROM police_stations
            WHERE ST_Contains(
                boundary,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
            )
            LIMIT 1
        """),
        {"lat": lat, "lon": lon}
    )
    containing_station = containing_result.fetchone()
    
    # Query 2: Find nearest station by lat/lon
    # nearest_result = await session.execute(
    #     text("""
    #         SELECT 
    #             id,
    #             name,
    #             address,
    #             lat,
    #             lon,
    #             ST_Distance(
    #                 ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
    #                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
    #             ) as distance_meters
    #         FROM police_stations
    #         WHERE lat IS NOT NULL AND lon IS NOT NULL
    #         ORDER BY ST_SetSRID(ST_MakePoint(lon, lat), 4326) <-> 
    #                  ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    #         LIMIT 1
    #     """),
    #     {"lat": lat, "lon": lon}
    # )
    # nearest_station = nearest_result.fetchone()
    
    return {
        "containing_station": {
            "id": str(containing_station.id),
            "name": containing_station.name,
            "address": containing_station.address,
            "lat": containing_station.lat,
            "lon": containing_station.lon,
            "pi_name": containing_station.pi_name,
            "pi_phone": containing_station.pi_phone,
            "zone": containing_station.zone,
            "distance_meters": float(containing_station.distance_meters)
        } if containing_station else {},
        # "nearest_station": {
        #     "id": str(nearest_station.id),
        #     "name": nearest_station.name,
        #     "address": nearest_station.address,
        #     "lat": nearest_station.lat,
        #     "lon": nearest_station.lon,
        #     "distance_meters": float(nearest_station.distance_meters)
        # } if nearest_station else {},
    }
    
import httpx
from fastapi import HTTPException
from src.config.settings import settings

async def send_message_to_user(message: str, phone: str):
    # # Send response to WhatsApp via WATI API
    WATI_API_BASE_URL = "https://live-mt-server.wati.io"
    wati_url = f"{WATI_API_BASE_URL}/{settings.WATI_TENANT_ID}/api/v1/sendSessionMessage/{phone}"
    
    async with httpx.AsyncClient() as http_client:
        try:
            wati_response = await http_client.post(
                wati_url,
                params={"messageText": message},
                headers={"Authorization": settings.WATI_API_ACCESS_TOKEN}
            )
        
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to send message via WATI: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Error connecting to WATI API: {str(e)}"
            )
    
    
async def extract_fields(
    user_message: str,
    assistant_message: str,
    session: dict
):
    ...
    

from sqlalchemy import update, and_, select
from src.models import ChatSessions
    
async def update_chat_session_with_extracted_data(
    db: AsyncSession,
    session_id: str,
    thread_id: str,
    function_args: dict
):
    name = function_args.get("name") or function_args.get("first_name")
    phone = function_args.get("phone_number")
    
    phone = f"+91{phone[-10:]}" if phone else None
    
    other_data_collected = {k: v for k, v in function_args.items() if k not in ["name", "first_name", "phone_number"]}
    
    await db.execute(
        update(ChatSessions)
            .where(and_(ChatSessions.session_id == session_id, ChatSessions.thread_id == thread_id))
            .values(
                collected_data=other_data_collected,
                name=name.capitalize() if name else None,
                phone=phone,
                lead_captured=name is not None and phone is not None
            )
    )
    await db.commit()
    
    
async def get_chat_sessions_db(
    db: AsyncSession,
    limit: int | None = 10,
    offset: int | None = 0
):
    result = await db.execute(
        select(ChatSessions)
            .where(ChatSessions.lead_captured == True)
            .order_by(ChatSessions.created_at.desc())
            .limit(limit)
            .offset(offset)
    )
    return result.scalars().all()