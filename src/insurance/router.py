from fastapi import APIRouter, HTTPException
from openai import OpenAI
import time

from src.config.settings import settings
from src.insurance.schemas import ChatRequest, ChatResponse
from src.insurance.session_store import get_or_create_thread, reset_session
from src.insurance.service import inject_initial_context


ASSISTANT_ID = settings.BAJAJ_INSURANCE_ASSISTANT_ID
client = OpenAI(api_key=settings.OPENAI_API_KEY)

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Assistant not configured")

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


@router.post("/reset")
def reset(session_id: str):
    reset_session(session_id)
    return {"status": "reset"}
