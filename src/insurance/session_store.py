import threading

sessions = {}
sessions_lock = threading.Lock()

def get_or_create_thread(session_id: str, goal: str | None, client):
    with sessions_lock:
        if session_id not in sessions:
            thread = client.beta.threads.create()
            sessions[session_id] = {
                "thread_id": thread.id,
                "goal": goal,
                "goal_injected": False
            }
        return sessions[session_id]


def reset_session(session_id):
    sessions.pop(session_id, None)