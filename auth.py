import os
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt  # type: ignore[import]
import bcrypt  # type: ignore[import]
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY: str = os.getenv("JWT_SECRET", "secret")
ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        plain_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bool(bcrypt.checkpw(plain_bytes, hashed_bytes))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed: bytes = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return str(jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM))
