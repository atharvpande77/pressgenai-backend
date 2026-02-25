import aioboto3

from src.config.settings import settings

session = aioboto3.Session(
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
    aws_account_id=settings.AWS_ACCOUNT_ID
)

async def get_s3_client():
    async with session.client('s3') as s3:
        yield s3

async def get_ddb_client():
    async with session.resource('dynamodb') as ddb:
        yield ddb
