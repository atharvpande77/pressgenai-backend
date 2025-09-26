from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file = '.env',
        env_file_encoding = 'utf-8'
    )

    POSTGRES_CNX_STR: str
    POSTGRES_CNX_STR_LOCAL: str
    # ENVIRONMENT: str
    SERP_API_KEY: str
    EXHAUSTED_SERP_API_KEY1: str
    EXHAUSTED_SERP_API_KEY2: str
    OPENAI_API_KEY: str
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str

settings = Settings()

