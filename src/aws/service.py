from fastapi import UploadFile
import time
import traceback
import mimetypes
from botocore.exceptions import ClientError

from src.config.settings import settings


def get_current_unix_timestamp():
    return int(time.time()*1000)

def get_full_file_key(prefix: str, filename: str):
    filename_without_ext, ext = filename.split('.')
    return f"{prefix}/{filename_without_ext}_{get_current_unix_timestamp()}.{ext}"

async def upload_file(
    s3,
    file: UploadFile,
    username: str,
    folder: str | None = "profile_images",
):
    try:
        filename = file.filename.strip()
        filename_without_extension, ext = filename.split('.')
        file_extension = ext if filename else 'jpg'
        key = f"{folder}/{username}/{filename_without_extension}_{get_current_unix_timestamp()}.{file_extension}"

        file_content = await file.read()

        response = await s3.put_object(
            Bucket=settings.PROFILE_IMAGE_S3_BUCKET,
            Key=key,
            Body=file_content,
            ContentType=file.content_type or 'application/octet-stream',
            # ACL='public-read'
        )
        print(response)

        await file.seek(0)
        return key
    except Exception as e:
        print(str(e))
        traceback.print_exc()
        return None
    
async def generate_presigned_urls(
    s3,
    prefix: str,
    filenames: list[str]
):
    urls = []
    for filename in filenames:
        try:
            key = get_full_file_key(prefix, filename)
            content_type, _ = mimetypes.guess_type(filename)
            if content_type is None:
                content_type = "application/octet-stream"  # Default fallback

            presigned_url = await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.PROFILE_IMAGE_S3_BUCKET,
                    "Key": key,
                    # "ContentType": content_type
                }
            )
            urls.append({
                "upload_url": presigned_url,
                "key": key
            })
        except ClientError:
            print(f"Error while generating presigned url for file: {filename}")
            urls.append({
                "upload_url": None,
                "key": key
            })
    
    return urls