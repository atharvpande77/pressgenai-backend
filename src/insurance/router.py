from fastapi import APIRouter, HTTPException, Request, Depends
from openai import OpenAI
import time
import httpx
from sse_starlette.sse import EventSourceResponse
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote_plus

from src.config.settings import settings
from src.insurance.schemas import ChatRequest, ChatResponse
from src.insurance.session_store import get_or_create_thread, reset_session
from src.insurance.service import inject_initial_context, get_police_helpdesk_response, check_if_message_after_ama, get_conversation_by_id
from src.config.database import get_session
from src.insurance.utils import parse_gps_coords

# ASSISTANT_ID = settings.BAJAJ_INSURANCE_ASSISTANT_ID
client = OpenAI(api_key=settings.OPENAI_API_KEY)

router = APIRouter()
TYPING_DELAY = 0.005  # seconds per character

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # if not ASSISTANT_ID:
        # raise HTTPException(status_code=500, detail="Assistant not configured")

    session = get_or_create_thread(req.session_id, req.goal, client)
    thread_id = session["thread_id"]

    # Inject goal only once
    if session["goal"] and not session.get("goal_injected"):
        inject_initial_context(thread_id, session["goal"], client)
        session["goal_injected"] = True

    # Add user message
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=req.message
    )

    # Run assistant
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID
    )

    # Poll until completion
    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        time.sleep(0.5)

    if run_status.status != "completed":
        raise HTTPException(status_code=500, detail="Assistant run failed")

    # Get latest assistant message
    messages = client.beta.threads.messages.list(thread_id=thread_id)

    for msg in messages.data:
        if msg.role == "assistant":
            return ChatResponse(reply=msg.content[0].text.value)

    raise HTTPException(status_code=500, detail="No assistant response found")


@router.get("/chat/stream")
async def stream_insurance_chat(session_id: str, message: str, goal: str | None = None):
    # if not ASSISTANT_ID:
    #     raise HTTPException(status_code=500, detail="Assistant not configured")

    session = get_or_create_thread(session_id, goal, client)
    thread_id = session["thread_id"]

    # Inject goal only once
    # if session["goal"] and not session.get("goal_injected"):
    #     inject_initial_context(thread_id, session["goal"], client)
    #     session["goal_injected"] = True
    
    
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=session.get("first_session_message", "")
    )
        
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )
    
    def event_generator():
        # Create run with streaming enabled
        with client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=session["assistant_id"]
        ) as stream:
            for event in stream:
                # We only care about incremental text
                if event.event == "thread.message.delta":
                    delta = event.data.delta
                    if delta.content:
                        for block in delta.content:
                            if block.type == "text":
                                for char in block.text.value:
                                    yield {
                                        "event": "message",
                                        "data": char
                                    }
                                    time.sleep(TYPING_DELAY)

                # End signal
                if event.event == "thread.run.completed":
                    yield {
                        "event": "done",
                        "data": ""
                    }

    return EventSourceResponse(event_generator())


@router.post("/reset")
def reset(session_id: str):
    reset_session(session_id)
    return {"status": "reset"}


async def send_payload_to_request_bin(body: dict):
    request_bin_url = "https://e649edf20eac5871b342g15gppeyyyyyb.oast.pro"
    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            request_bin_url,
            json=body,
            headers={"Content-Type": "application/json"}
        )

from src.insurance.utils import parse_gps_coords
from src.insurance.service import get_curr_location_jurisdiction_and_nearest_station, send_message_to_user

@router.post("/police/wati/chat/webhook")
async def police_whatsapp_chat_webhook(request: Request, session: Annotated[AsyncSession, Depends(get_session)]):
    """
    Webhook endpoint for police WhatsApp chat via WATI.
    Expects JSON body with 'message', 'waId', and optional 'language' fields.
    """
    body = await request.json()

    message = body.get("text")
    phone = body.get("waId")
    message_type = body.get("type")
        # conversation_id = body.get("conversationId")
    
    # await send_payload_to_request_bin(body)
    
    if not message or not phone:
        return {"status": "ignored"}
    
    message_lower = message.lower()
    # Get GPT response
    if len(phone) == 10:
        phone = "+91" + phone
    
    BLOCKED_INPUTS = {"hi", "start", "hello", "exit"}
    
    if message_type == 'text' and message_lower not in BLOCKED_INPUTS:
        gpt_response = await get_police_helpdesk_response(query=message)
        
        await send_message_to_user(message=gpt_response, phone=phone)
                
        return {"status": "sent"}

    if message_type == 'location':
        lat, lon = parse_gps_coords(message)
        if not lat:
            raise HTTPException(status_code=400, detail="Invalid GPS coordinates")
        
        try:
            station_info = await get_curr_location_jurisdiction_and_nearest_station(session, lat, lon)
        except Exception as e:
            await send_payload_to_request_bin({"type": "location", "lat": lat, "lon": lon, "error": str(e)})
        
        # Nearest police station: {nearest_station.get("name", "unknown")} ({(nearest_station.get("distance_meters", 0)/1000).__format__(".2f")} km away)
        #         Google Maps Link: {f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(nearest_station.get("address", 'N/A'))}&travelmode=driving&dir_action=navigate" if nearest_station else 'N/A'}
        
        try:
            juridiction_station = station_info.get("containing_station", {})
            # nearest_station = station_info.get("nearest_station", {})
            
            final_message = f"""🚓 *Your Current Jurisdiction*

📍 *Station:* {juridiction_station.get("name", "Unknown")}
📏 *Distance:* {(juridiction_station.get("distance_meters", 0)/1000):.2f} km away

👮 *Police Inspector (PI)*
- Name: {juridiction_station.get("pi_name", "N/A")}
- Phone: {juridiction_station.get("pi_phone", "N/A")}

🗺️ *Location Details*
- Zone: {juridiction_station.get("zone", "N/A")}
- Address: {juridiction_station.get("address", "N/A")}

📌 *Navigate:*
{f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(juridiction_station.get('address', 'N/A'))}&travelmode=driving&dir_action=navigate" if juridiction_station.get("address") else "N/A"}
            """
        except Exception as e:
            await send_payload_to_request_bin({"type": "location", "lat": lat, "lon": lon, "station_info": station_info, "error": str(e)})
        
        try:
            await send_message_to_user(message=final_message, phone=phone)
        except Exception as e:
            await send_payload_to_request_bin({"final_message": final_message})
        
        return {"status": "sent"}
        
    return {"status": "ignored"}
        
    
