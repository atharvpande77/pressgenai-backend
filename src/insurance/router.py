from fastapi import APIRouter, HTTPException, Request
from openai import OpenAI
import time
import httpx
from sse_starlette.sse import EventSourceResponse

from src.config.settings import settings
from src.insurance.schemas import ChatRequest, ChatResponse
from src.insurance.session_store import get_or_create_thread, reset_session
from src.insurance.service import inject_initial_context, get_police_helpdesk_response


# ASSISTANT_ID = settings.BAJAJ_INSURANCE_ASSISTANT_ID
client = OpenAI(api_key=settings.OPENAI_API_KEY)

router = APIRouter()
TYPING_DELAY = 0.005  # seconds per character
WATI_API_BASE_URL = "https://live-mt-server.wati.io"

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


@router.post("/police/wati/chat/webhook/{phone}")
async def police_whatsapp_chat_webhook(language: str, phone: str, request: Request):
    """
    Webhook endpoint for police WhatsApp chat via WATI.
    Expects JSON body with 'message', 'waId', and optional 'language' fields.
    """
    body = await request.json()

    if body:
        message = body.get("text", "")
    else:
        message = ""
    
    # message = body.get("text", "")
    # language = body.get("language", "English")
    # wa_id = body.get("waId")
    
    # if not message:
    #     raise HTTPException(status_code=400, detail="Message is required")
    
    # if not wa_id:
    #     raise HTTPException(status_code=400, detail="waId is required")
    
    # Get GPT response
    if len(phone) == 10:
        phone = "+91" + phone
    gpt_response = await get_police_helpdesk_response(query=message, language=language)
    
    # Send response to WhatsApp via WATI API
    wati_url = f"{WATI_API_BASE_URL}/{settings.WATI_TENANT_ID}/api/v1/sendSessionMessage/{phone}"
    
    async with httpx.AsyncClient() as http_client:
        wati_response = await http_client.post(
            wati_url,
            params={"messageText": gpt_response},
            headers={"Authorization": settings.WATI_API_ACCESS_TOKEN}
        )
        
        if wati_response.status_code != 200:
            raise HTTPException(
                status_code=502, 
                detail=f"Failed to send message via WATI: {wati_response.text}"
            )
    
    return {"reply": gpt_response, "wati_status": "sent"}