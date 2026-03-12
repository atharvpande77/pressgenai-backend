import aioboto3
import os

from src.config.settings import settings

if settings.ENV != "dev":
    # In cloud envs, prevent boto from trying a local named profile.
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_DEFAULT_PROFILE", None)

session_kwargs = {
    "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
    "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
    "region_name": settings.AWS_REGION,
}

session = aioboto3.Session(**session_kwargs)

async def get_s3_client():
    async with session.client('s3') as s3:
        yield s3

async def get_ddb_client():
    async with session.resource('dynamodb') as ddb:
        yield ddb
