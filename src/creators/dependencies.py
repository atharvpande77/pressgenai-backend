from fastapi import UploadFile, File, HTTPException, status
from typing import Optional


ALLOWED_IMAGE_TYPES = [
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'image/gif',
    'image/avif',
]

async def validate_profile_image(
    profile_image: Optional[list[UploadFile]] = File(None)
) -> Optional[UploadFile]:
    """
    Dependency to validate profile image file type and size (max 2MB)
    """
    if profile_image is None:
        return None
    
    print(len(profile_image), "no of files")
    if len(profile_image) > 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="only 1 image file allowed"
        )
    
    profile_image = profile_image[0]
    
    # Check file type
    if profile_image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )
    
    # Check file size (2MB limit)
    file_size = 0
    chunk_size = 1024 * 1024  # 1MB
    max_size = 10 * 1024 * 1024  # 2MB
    
    for chunk in iter(lambda: profile_image.file.read(chunk_size), b""):
        file_size += len(chunk)
        if file_size > max_size:
            raise HTTPException(
                status_code=400,
                detail="File too large. Maximum size is 10MB"
            )
    
    # Reset file pointer after reading
    profile_image.file.seek(0)
    
    return profile_image