import os

# src.config.settings requires these at import time; unit tests never touch real services.
for key in [
    "SERP_API_KEY", "EXHAUSTED_SERP_API_KEY1", "EXHAUSTED_SERP_API_KEY2", "OPENAI_API_KEY",
    "JWT_SECRET", "JWT_REFRESH_SECRET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ACCOUNT_ID",
    "RETIREMENT_PLANNING_ASSISTANT_ID", "TERM_INSURANCE_ASSISTANT_ID", "CHILD_EDUCATION_PLANNING_ASSISTANT_ID",
    "TAX_PLANNING_ASSISTANT_ID", "WATI_API_ACCESS_TOKEN", "WATI_TENANT_ID",
]:
    os.environ.setdefault(key, "test")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("PROFILE_IMAGE_S3_BUCKET", "pressgenai-media")
os.environ.setdefault("POSTGRES_CNX_STR_LOCAL", "postgresql+asyncpg://test:test@localhost:1/test")
