from openai import OpenAI, AsyncOpenAI

from src.config.settings import settings


timeout = 60
retries = 3

openai_sync_client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=timeout,
    max_retries=retries
)

openai_async_client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=timeout,
    max_retries=retries
)