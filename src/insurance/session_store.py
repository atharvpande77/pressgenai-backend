import threading
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select
from openai import AsyncClient

from src.models import ChatSessions
from src.config.settings import settings

sessions = {}
sessions_lock = threading.Lock()

assistant_id_map = {
    "retirement": {
        "assistant_id": settings.RETIREMENT_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        👋 Hello!
        I am the digital assistant for Mr. Varad Joshi, a renowned financial planner.
        I will help you plan your retirement in a simple and structured way.

        Please choose your preferred language:
        English | Hindi | Marathi
        """
    },
    "child_education": {
        "assistant_id": settings.CHILD_EDUCATION_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        👋 Hello!
        I am the digital assistant for Mr. Varad Joshi, a renowned financial planner.
        I will help you plan your child's education in a simple and structured way.

        Please choose your preferred language:
        English | Hindi | Marathi
        """
    },
    "term_insurance": {
        "assistant_id": settings.TERM_INSURANCE_ASSISTANT_ID,
        "first_session_message": """
        👋 Hello!
        I am the digital assistant for Mr. Varad Joshi, a renowned financial planner.
        I will help you plan your term insurance in a simple and structured way.

        Please choose your preferred language:
        English | Hindi | Marathi
        """
    },
    "tax": {
        "assistant_id": settings.TAX_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        👋 Hello!
        I am the digital assistant for Mr. Varad Joshi, a renowned financial planner.
        I will help you plan your taxes in a simple and structured way.

        Please choose your preferred language:
        English | Hindi | Marathi
        """
    },
    "savings": {
        "assistant_id": settings.RETIREMENT_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        👋 Hello!
        I am the digital assistant for Mr. Varad Joshi, a renowned financial planner.
        I will help you plan your savings in a simple and structured way.

        Please choose your preferred language:
        English | Hindi | Marathi
        """
    }
}



# def get_or_create_thread(session_id: str, goal: str | None, client):
#     with sessions_lock:
#         if session_id not in sessions:
#             thread = client.beta.threads.create()
#             sessions[session_id] = {
#                 "thread_id": thread.id,
#                 "goal": goal,
#                 "first_message_injected": False,
#                 "assistant_id": assistant_id_map.get(goal, {}).get("assistant_id", settings.RETIREMENT_PLANNING_ASSISTANT_ID),
#                 "first_session_message": assistant_id_map.get(goal, {}).get("first_session_message", assistant_id_map["retirement"]["first_session_message"])
#             }
#         return sessions[session_id]

async def get_or_create_thread(
    db: AsyncSession,
    session_id: str,
    goal: str | None,
    client: AsyncClient
):
    assistant_id = assistant_id_map.get(goal, {}).get("assistant_id")
    # print(f"Assistant ID for goal '{goal}': {assistant_id}")
    
    # print(f"Checking for existing session with ID: {session_id}")
    result = await db.execute(
        select(ChatSessions)
            .where(ChatSessions.session_id == session_id)
    )
    
    existing = result.scalar_one_or_none()
    # print(f"Existing session: {existing}")
    
    if not existing:
        thread = await client.beta.threads.create(
            messages=[{"role": "assistant", "content": assistant_id_map.get(goal, {}).get("first_session_message", assistant_id_map["retirement"]["first_session_message"])}]
        )
        
        result = await db.execute(
            insert(ChatSessions)
                .values(
                    session_id=session_id,
                    thread_id=thread.id,
                    assistant_id=assistant_id,
                    goal=goal
                )
                .returning(ChatSessions)
        )
        await db.commit()
        chat_session = result.scalar_one_or_none()
        return chat_session
        
    return existing