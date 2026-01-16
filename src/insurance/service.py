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
                "content": f"{POLICE_HELPDESK_SYSTEM_PROMPT}"
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


TABLE_NAME = "police_whatapp_bot_session_store"


async def check_if_message_after_ama(ddb, conversation_id: str, message: str) -> bool:
    """
    Tracks if "Ask me anything!" has been reached in a conversation.
    Also sets the language based on which trigger message was received.
    Returns True if conversation is past AMA state (should call GPT).
    Returns False if AMA not yet reached (should NOT call GPT).
    """
    table = await ddb.Table(TABLE_NAME)
    
    if message.lower() == "ask me anything!":
        await table.put_item(Item={
            "conversation_id": conversation_id,
            "ama_reached": True,
            "language": "English"
        })
        return False
    
    if message == "कोणतेही प्रश्न विचारा":
        await table.put_item(Item={
            "conversation_id": conversation_id,
            "ama_reached": True,
            "language": "Marathi"
        })
        return False
    
    # Check if ama_reached is True in DynamoDB
    response = await table.get_item(Key={"conversation_id": conversation_id})
    item = response.get("Item", {})
    return item.get("ama_reached", False)


async def get_conversation_by_id(ddb, conversation_id: str) -> dict:
    """Returns the conversation data from DynamoDB, defaults to empty dict."""
    table = await ddb.Table(TABLE_NAME)
    response = await table.get_item(Key={"conversation_id": conversation_id})
    return response.get("Item", {"language": "English"})