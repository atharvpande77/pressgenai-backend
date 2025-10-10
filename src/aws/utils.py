from src.config.settings import settings

bucket = settings.PROFILE_IMAGE_S3_BUCKET
region = settings.AWS_REGION

def get_full_s3_object_url(key: str | None = None):
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}" if key else None

def get_bucket_base_url():
    return f"https://{settings.PROFILE_IMAGE_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/"

def get_images_with_urls(keys: list[str] | None = None):
    if not keys:
        return []
    return [{"url": get_full_s3_object_url(key), "key": key} for key in keys]
