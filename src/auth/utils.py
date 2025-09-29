import bcrypt
from datetime import timedelta, datetime
import jwt
import traceback

from src.config.settings import settings

ALGO = 'HS256'

def verify_pw(pw: str, hashed: str):
    return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))

def create_tokens(data: dict, access_exp_delta: timedelta | None = None, refresh_exp_delta: timedelta | None = None):
    to_encode = data.copy()

    access_expire = datetime.now() + access_exp_delta if access_exp_delta else timedelta(minutes=15)
    refresh_expire = datetime.now() + refresh_exp_delta if refresh_exp_delta else timedelta(minutes=15)
    
    access_token = jwt.encode(
        {**to_encode, 'exp': access_expire},
        settings.JWT_SECRET,
        ALGO
    )
    refresh_token = jwt.encode(
        {**to_encode, 'exp': refresh_expire},
        settings.JWT_REFRESH_SECRET,
        ALGO
    )
    return access_token, refresh_token

def decrypt_jwt(token: str):
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            ALGO
        )
        return payload
    except jwt.exceptions.ExpiredSignatureError as e:
        print(e)
        return None
    except jwt.exceptions.DecodeError as e:
        print(e)
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Unknown exception while decrypting JWT: {e}")
        traceback.print_exc()
        return None
    
