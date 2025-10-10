from sqlalchemy import func, case, literal, or_, select, text
from sqlalchemy.dialects.postgresql import array, JSONB
from uuid import UUID

from src.models import Users, GeneratedUserStories
from src.aws.utils import get_bucket_base_url


creator_profile_image = case(
        (Users.profile_image_key != None,
        func.concat(
            literal(get_bucket_base_url()),
            Users.profile_image_key
        )),
        else_=None
    ).label("creator_profile_image")

editor_profile_image = case(
        (Users.profile_image_key != None,
        func.concat(
            literal(get_bucket_base_url()),
            Users.profile_image_key
        )),
        else_=None
    ).label("editor_profile_image")


def get_article_images_json_query():
    unnested_images = (
        select(
            GeneratedUserStories.id.label('story_id'),
            func.unnest(GeneratedUserStories.images_keys).label('image_key')
        )
        .subquery('unnested_images')
    )

    return (
        select(
            func.coalesce(
                func.jsonb_agg(
                    func.jsonb_build_object(
                        'key', unnested_images.c.image_key,
                        'url', func.concat(get_bucket_base_url(), unnested_images.c.image_key)
                    )
                ),
                text("'[]'::jsonb")  # Use text() with proper PostgreSQL casting
            )
        )
        .where(unnested_images.c.story_id == GeneratedUserStories.id)
        .correlate(GeneratedUserStories)
        .scalar_subquery()
        .label('images')
    )