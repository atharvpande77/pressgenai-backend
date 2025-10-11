from sqlalchemy import func, case, literal, or_, select, text
from sqlalchemy.dialects.postgresql import array, JSONB
from uuid import UUID

from src.models import Users, GeneratedUserStories
from src.aws.utils import get_bucket_base_url


# creator_profile_image = case(
#         (Users.profile_image_key != None,
#         func.concat(
#             literal(get_bucket_base_url()),
#             Users.profile_image_key
#         )),
#         else_=None
#     ).label("creator_profile_image")

# editor_profile_image = case(
#         (Users.profile_image_key != None,
#         func.concat(
#             literal(get_bucket_base_url()),
#             Users.profile_image_key
#         )),
#         else_=None
#     ).label("editor_profile_image")

def get_profile_image_expression(
    user_table_or_alias=None, 
    label_name: str = "profile_image"
):
    """
    Generate a profile image URL expression for any Users table or alias.
    
    Args:
        user_table_or_alias: The Users table or an aliased version. 
                           If None, uses the base Users model.
        label_name: The label to use for the resulting column
    
    Returns:
        A SQLAlchemy case expression with the specified label
    """
    # Import here to avoid circular imports
    from src.models import Users
    
    table = user_table_or_alias if user_table_or_alias is not None else Users
    
    return case(
        (table.profile_image_key != None,
         func.concat(
             literal(get_bucket_base_url()),
             table.profile_image_key
         )),
        else_=None
    ).label(label_name)


def get_creator_profile_image(creator_table_or_alias=None):
    """
    Get profile image expression for a creator (author) table/alias.
    
    Args:
        creator_table_or_alias: Optional aliased Users table for creators.
                               If None, uses base Users model.
    """
    return get_profile_image_expression(creator_table_or_alias, "creator_profile_image")


def get_editor_profile_image(editor_table_or_alias=None):
    """
    Get profile image expression for an editor table/alias.
    
    Args:
        editor_table_or_alias: Optional aliased Users table for editors.
                              If None, uses base Users model.
    """
    return get_profile_image_expression(editor_table_or_alias, "editor_profile_image")


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