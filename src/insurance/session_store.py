import threading
from src.config.settings import settings

sessions = {}
sessions_lock = threading.Lock()

assistant_id_map = {"retirement": settings.RETIREMENT_PLANNING_ASSISTANT_ID, "child_education": settings.CHILD_EDUCATION_PLANNING_ASSISTANT_ID, "term_insurance": settings.TERM_INSURANCE_ASSISTANT_ID}

def get_or_create_thread(session_id: str, goal: str | None, client):
    with sessions_lock:
        if session_id not in sessions:
            thread = client.beta.threads.create()
            sessions[session_id] = {
                "thread_id": thread.id,
                "goal": goal,
                "goal_injected": False,
                "assistant_id": assistant_id_map.get(goal, settings.RETIREMENT_PLANNING_ASSISTANT_ID)
            }
        return sessions[session_id]


def reset_session(session_id):
    sessions.pop(session_id, None)