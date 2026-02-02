import threading
from src.config.settings import settings

sessions = {}
sessions_lock = threading.Lock()

assistant_id_map = {
    "retirement": {
        "assistant_id": settings.RETIREMENT_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        👋 Hi  
        I'm the digital assistant for Mr. Rahul Verma, a licensed life insurance advisor with Bajaj Life Insurance, with over 7 years of experience.

        📋 **Just so you know:** This is for awareness and education only. All numbers are indicative and based on your inputs. No actual selling - just helpful guidance.

        Before we begin, please choose your language:
        🇬🇧 English / 🇮🇳 Hindi / 🇮🇳 Marathi?
        """
    },
    "child_education": {
        "assistant_id": settings.CHILD_EDUCATION_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        Hello! I'm here to help you plan for your child's education. Let's explore the best options for their future.
        
        📋 **Just so you know:** This is for awareness and education only. All numbers are indicative and based on your inputs. No actual selling - just helpful guidance.
        
        May I know your name please?
        """
    },
    "term_insurance": {
        "assistant_id": settings.TERM_INSURANCE_ASSISTANT_ID,
        "first_session_message": """
        👋 Hello  

        I’m the digital assistant for Mr. Rahul Verma, a licensed life insurance advisor with Bajaj Life Insurance, with over 7 years of experience.
        
        📋 **Just so you know:** This is for awareness and education only. All numbers are indicative and based on your inputs. No actual selling - just helpful guidance.

        Before we begin, which language are you most comfortable with?
        English / Hindi / Marathi"""
    },
    "tax": {
        "assistant_id": settings.TAX_PLANNING_ASSISTANT_ID,
        "first_session_message": """
        Hi! 👋  
        
        I’m the digital assistant for Mr. Rahul Verma, a licensed life insurance advisor with Bajaj Life Insurance, with over 7 years of experience.
        
        📋 **Just so you know:** This is for awareness and education only. All numbers are indicative and based on your inputs. No actual selling - just helpful guidance.
        
        It’ll take just 2–3 minutes. Shall we begin?
        """
    }
}



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