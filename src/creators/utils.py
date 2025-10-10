import bcrypt

def hash_password(password: str):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    return hashed

async def get_presigned_s3_url(username: str, filename: str, file_type: str):
    ...