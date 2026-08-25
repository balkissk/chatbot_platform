import hashlib
import hmac
import os
import secrets
import time
from typing import Any
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from config.settings import load_environment
from database.db import SessionLocal
from models.user import User


ENVIRONMENT = load_environment()
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if ENVIRONMENT == "production":
        raise RuntimeError("JWT_SECRET is required in production.")
    JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_SECONDS = 15 * 60
AUTH_COOKIE_NAME = "chatbot_factory_session"
ALLOWED_ROLES = {"admin", "manager", "end_user"}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    salt_value = jwt.utils.base64url_encode(salt).decode()
    digest_value = jwt.utils.base64url_encode(digest).decode()
    return f"pbkdf2_sha256${salt_value}${digest_value}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_value, digest_value = password_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    salt = jwt.utils.base64url_decode(salt_value.encode())
    expected_digest = jwt.utils.base64url_decode(digest_value.encode())
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        200_000
    )

    return hmac.compare_digest(actual_digest, expected_digest)


def validate_password_policy(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not any(char.isupper() for char in password):
        raise ValueError("Password must include at least one uppercase letter")
    if not any(char.islower() for char in password):
        raise ValueError("Password must include at least one lowercase letter")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must include at least one number")
    return password


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": int(time.time()) + JWT_EXPIRES_SECONDS
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=JWT_EXPIRES_SECONDS,
        httponly=True,
        secure=ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def normalize_role(role: str) -> str:
    role = role.strip().lower()
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    return role


def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=AUTH_COOKIE_NAME)] = None,
    db: Session = Depends(get_db)
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(session_token)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()

    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Inactive or missing user")

    return user


def require_roles(*roles: str):
    allowed = set(roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(status_code=403, detail="You do not have permission to access this resource.")
        return current_user

    return dependency
