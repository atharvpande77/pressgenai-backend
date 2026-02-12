from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ChatRequest(BaseModel):
    session_id: str
    message: str
    goal: str | None = None

class ChatResponse(BaseModel):
    reply: str
    
    
class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    session_id: str
    name: str | None = None
    phone: str | None = None
    collected_data: dict | None = None
    goal: str | None = None
    created_at: datetime
    