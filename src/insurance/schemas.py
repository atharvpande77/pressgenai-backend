from pydantic import BaseModel

class ChatRequest(BaseModel):
    session_id: str
    message: str
    goal: str | None = None

class ChatResponse(BaseModel):
    reply: str