from fastapi import APIRouter, HTTPException
from openai import OpenAI
import time
from sse_starlette.sse import EventSourceResponse

from src.config.settings import settings
from src.insurance.schemas import ChatRequest, ChatResponse
from src.insurance.session_store import get_or_create_thread, reset_session
from src.insurance.service import inject_initial_context


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
