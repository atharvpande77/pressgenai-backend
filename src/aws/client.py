import aioboto3

from src.config.settings import settings

session = aioboto3.Session(
    profile_name=settings.AWS_PROFILE
)

async def get_s3_client():
    async with session.client('s3') as s3:
        yield s3

async def get_ddb_client():
    async with session.resource('dynamodb') as ddb:
        yield ddb
