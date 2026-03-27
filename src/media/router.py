from fastapi import APIRouter, Depends
from typing import Annotated

from src.media.schemas import ArticleImagesRequest
from src.models import GeneratedUserStories
from src.aws.client import get_s3_client
from src.media.service import check_article_authorization, get_article_image_prefix
from src.aws.service import generate_presigned_urls

router = APIRouter()


@router.post('/articles/{generated_article_id}/images')
async def get_images_upload_urls(
    article_db: Annotated[GeneratedUserStories, Depends(check_article_authorization)],
    request: ArticleImagesRequest,
    s3=Depends(get_s3_client)
):
    filenames = list(set(request.filenames))
    
    prefix = get_article_image_prefix(article_db)

    upload_urls: list[dict] = await generate_presigned_urls(
        s3,
        prefix,
        filenames
    )
    return upload_urls