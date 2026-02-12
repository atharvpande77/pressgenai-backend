from fastapi import APIRouter, HTTPException, Request, Depends
from openai import OpenAI
import time
import httpx
from sse_starlette.sse import EventSourceResponse
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote_plus

from src.config.settings import settings
from src.insurance.schemas import ChatRequest, ChatResponse, ChatSessionResponse
from src.insurance.session_store import get_or_create_thread
from src.insurance.service import inject_initial_context, get_police_helpdesk_response, check_if_message_after_ama, get_conversation_by_id, update_chat_session_with_extracted_data, get_chat_sessions_db
from src.config.database import get_session
from src.insurance.utils import parse_gps_coords
from src.config.database import get_session

from src.config.openai_client import openai_async_client

# ASSISTANT_ID = settings.BAJAJ_INSURANCE_ASSISTANT_ID
# client = OpenAI(api_key=settings.OPENAI_API_KEY)
Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter()
TYPING_DELAY = 0.001  # seconds per character


async def cancel_active_runs(thread_id: str):
    """
    Check for any active runs on the thread and cancel them.
    This prevents the "Can't add messages to thread while a run is active" error.
    """
    try:
        runs = await openai_async_client.beta.threads.runs.list(thread_id=thread_id, limit=10)
        for run in runs.data:
            if run.status in ["in_progress", "queued", "requires_action", "pending"]:
                try:
                    await openai_async_client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run.id)
                    # Wait briefly for cancellation to take effect
                    max_wait = 5  # max 5 seconds
                    waited = 0
                    while waited < max_wait:
                        run_status = await openai_async_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                        if run_status.status in ["cancelled", "failed", "completed", "expired"]:
                            break
                        time.sleep(0.3)
                        waited += 0.3
                except Exception as e:
                    print(f"Failed to cancel run {run.id}: {e}")
    except Exception as e:
        print(f"Error checking for active runs: {e}")

# @router.post("/chat", response_model=ChatResponse)
# def chat(req: ChatRequest, session: Session):
#     # if not ASSISTANT_ID:
#         # raise HTTPException(status_code=500, detail="Assistant not configured")

#     session = get_or_create_thread(req.session_id, req.goal, client)
#     thread_id = session["thread_id"]

#     # Inject goal only once
#     if session["goal"] and not session.get("goal_injected"):
#         inject_initial_context(thread_id, session["goal"], client)
#         session["goal_injected"] = True

#     # Add user message
#     client.beta.threads.messages.create(
#         thread_id=thread_id,
#         role="user",
#         content=req.message
#     )

#     # Run assistant
#     run = client.beta.threads.runs.create(
#         thread_id=thread_id,
#         assistant_id=ASSISTANT_ID
#     )

#     # Poll until completion
#     while True:
#         run_status = client.beta.threads.runs.retrieve(
#             thread_id=thread_id,
#             run_id=run.id
#         )
#         if run_status.status in ["completed", "failed", "cancelled"]:
#             break
#         time.sleep(0.5)

#     if run_status.status != "completed":
#         raise HTTPException(status_code=500, detail="Assistant run failed")

#     # Get latest assistant message
#     messages = client.beta.threads.messages.list(thread_id=thread_id)

#     for msg in messages.data:
#         if msg.role == "assistant":
#             return ChatResponse(reply=msg.content[0].text.value)

#     raise HTTPException(status_code=500, detail="No assistant response found")


@router.get("/chat/stream")
async def stream_insurance_chat(
    db: Session,
    session_id: str,
    message: str,
    goal: str | None = None
):
    # if not ASSISTANT_ID:
    #     raise HTTPException(status_code=500, detail="Assistant not configured")

    chat_session = await get_or_create_thread(db, session_id, goal, openai_async_client)
    
    thread_id = chat_session.thread_id

    # Cancel any active runs before adding new messages
    await cancel_active_runs(thread_id)

    # Inject icebreaker message only once
    # if session["goal"] and not session.get("first_message_injected"):
    #     client.beta.threads.messages.create(
    #         thread_id=thread_id,
    #         role="assistant",
    #         content=session.get("first_session_message", "")
    #     )
    #     session["first_message_injected"] = True
    
    await openai_async_client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )
    
    async def event_generator():
    # Create run with streaming enabled
        tool_calls = []
        # current_tool_call_index = None
        
        async with openai_async_client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=chat_session.assistant_id
        ) as stream:
            async for event in stream:
                # Handle text deltas
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
                
                # Handle function call requests
                if event.event == "thread.run.requires_action":
                    # Extract the tool calls
                    required_action = event.data.required_action
                    
                    if required_action.type == "submit_tool_outputs":
                        tool_calls = required_action.submit_tool_outputs.tool_calls
                        
                        # Process each tool call
                        tool_outputs = []
                        for tool_call in tool_calls:
                            if tool_call.function.name == "extract_user_data":
                                # Parse the function arguments
                                import json
                                import re
                                function_args = json.loads(tool_call.function.arguments)
                                
                                print(f"[extract_user_data] User message: '{message}'")
                                print(f"[extract_user_data] Received args: {function_args}")
                                
                                # Validate that extracted values actually exist in the user's message
                                # This prevents the assistant from fabricating values
                                def validate_extraction(args: dict, user_message: str) -> bool:
                                    """Check if any extracted numeric value is actually in the user's message."""
                                    user_msg_lower = user_message.lower().strip()
                                    
                                    # Extract all numbers from the user's message
                                    numbers_in_message = set(re.findall(r'\d+', user_message))
                                    
                                    # If user just selected language, no numeric data should be extracted
                                    language_responses = {'english', 'hindi', 'marathi', 'en', 'hi', 'mr'}
                                    if user_msg_lower in language_responses:
                                        return False
                                    
                                    # Check if any extracted numeric value matches numbers in the message
                                    for key, value in args.items():
                                        if value is None or value == "":
                                            continue
                                        
                                        # For numeric fields, verify the number exists in message
                                        if key in ['age', 'annual_income', 'num_dependents', 'loan_amount']:
                                            if isinstance(value, (int, float)) and value > 0:
                                                # Check if this number or a reasonable variant exists
                                                value_str = str(int(value))
                                                if not any(num in value_str or value_str in num for num in numbers_in_message):
                                                    # Number not found in message - likely fabricated
                                                    print(f"[extract_user_data] REJECTED: {key}={value} not found in message")
                                                    return False
                                        
                                        # For phone number, verify format exists
                                        if key == 'phone_number' and value:
                                            if value not in user_message:
                                                print(f"[extract_user_data] REJECTED: phone not found in message")
                                                return False
                                        
                                        # For first_name, verify it's mentioned
                                        if key == 'first_name' and value:
                                            if value.lower() not in user_msg_lower:
                                                print(f"[extract_user_data] REJECTED: name not found in message")
                                                return False
                                    
                                    return True
                                
                                await update_chat_session_with_extracted_data(db, session_id, thread_id, function_args)
                                is_valid = validate_extraction(function_args, message)
                                
                                if is_valid:
                                    # Valid data that matches user input
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({"status": "success", "message": "Data captured successfully"})
                                    })
                                    
                                    
                                else:
                                    # Data doesn't match user's message - reject it
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({
                                            "status": "error",
                                            "message": "ERROR: The user has not provided this information yet. Do NOT extract data the user has not explicitly stated. Ask the question and wait for the user's response in the next message."
                                        })
                                    })
                        
                        # Submit the tool outputs back to continue the run
                        async with openai_async_client.beta.threads.runs.submit_tool_outputs_stream(
                            thread_id=thread_id,
                            run_id=event.data.id,
                            tool_outputs=tool_outputs
                        ) as tool_stream:
                            # Continue streaming the assistant's response
                            async for tool_event in tool_stream:
                                if tool_event.event == "thread.message.delta":
                                    delta = tool_event.data.delta
                                    if delta.content:
                                        for block in delta.content:
                                            if block.type == "text":
                                                for char in block.text.value:
                                                    yield {
                                                        "event": "message",
                                                        "data": char
                                                    }
                                                    time.sleep(TYPING_DELAY)
                                
                                if tool_event.event == "thread.run.completed":
                                    yield {
                                        "event": "done",
                                        "data": ""
                                    }
                
                # End signal (only if no tool calls were made)
                if event.event == "thread.run.completed":
                    yield {
                        "event": "done",
                        "data": ""
                    }
                    
    # print(f"Chat response for user message '{message}': {chat_response}")

    return EventSourceResponse(event_generator())


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
async def get_chat_sessions(
    db: Session,
    limit: int | None = 10,
    offset: int | None = 0
):
    chat_sessions = await get_chat_sessions_db(db, limit, offset)
    return chat_sessions


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
        
    
