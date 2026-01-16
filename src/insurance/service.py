import openai
from src.config.settings import settings

client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

POLICE_HELPDESK_SYSTEM_PROMPT = """You are an official Nagpur City Police helpdesk assistant.

Answer only general informational queries asked under "Other Enquiry".
Do NOT handle emergencies, complaints, FIRs, legal accusations, or urgent situations.
If the message is urgent or a complaint, instruct the user to contact the nearest police station or dial 112.

Respond in the same language as the user (English or Marathi).
Keep replies clear, polite, and concise.
Do not speculate or give legal advice.
If information is unavailable, say so clearly."""


async def get_police_helpdesk_response(query: str, language: str = "English") -> str:
    """
    Calls OpenAI chat completions API to get a response for police helpdesk queries.
    
    Args:
        query: The user's question/message
        language: The language to respond in (English or Marathi)
    
    Returns:
        The assistant's response text
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"{POLICE_HELPDESK_SYSTEM_PROMPT}\n\nRespond in {language}."
            },
            {
                "role": "user",
                "content": query
            }
        ],
        temperature=0.3,
        max_tokens=500
    )
    
    return response.choices[0].message.content

def inject_initial_context(thread_id: str, goal: str, client):
    goal_map = {
        "retirement": "Retirement planning",
        "child_education": "Child education planning",
        "savings": "Savings with protection",
        "human_life_value": "Human Life Value assessment"
    }

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=f"""
            The user has already selected the primary planning objective as:
            {goal_map.get(goal, goal)}.

            Do NOT ask the user to choose a planning goal again.
            Proceed with questions relevant to this objective only.
            """
    )


conversations = {}

def check_if_message_after_ama(conversation_id: str, message: str):
    if message == "Ask Me Anything!":
        conversations[conversation_id]["ama_reached"] = True
        return False
    return conversations.get(conversation_id, {}).get("ama_reached", False) 