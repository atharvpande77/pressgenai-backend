from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file = '.env',
        env_file_encoding = 'utf-8'
    )

    POSTGRES_CNX_STR_LOCAL: Optional[str] = None
    ENV: str
    DEV_DB_CNX_STR: Optional[str] = None
    SERP_API_KEY: str
    EXHAUSTED_SERP_API_KEY1: str
    EXHAUSTED_SERP_API_KEY2: str
    OPENAI_API_KEY: str
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str
    
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_ACCOUNT_ID: str
    AWS_REGION: str
    AWS_PROFILE: Optional[str] = None
    PROFILE_IMAGE_S3_BUCKET: str
    
    RETIREMENT_PLANNING_ASSISTANT_ID: str
    TERM_INSURANCE_ASSISTANT_ID: str
    CHILD_EDUCATION_PLANNING_ASSISTANT_ID: str
    TAX_PLANNING_ASSISTANT_ID: str

    WATI_API_ACCESS_TOKEN: str
    WATI_TENANT_ID: str

settings = Settings()

