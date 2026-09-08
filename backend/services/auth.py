import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from config.settings import load_environment
from database.db import SessionLocal
from models.auth_session import AuthSession
from models.user import User


ENVIRONMENT = load_environment()
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if ENVIRONMENT == "production":
        raise RuntimeError("JWT_SECRET is required in production.")
    JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_SECONDS = 60 * 60
REFRESH_TOKEN_EXPIRES_SECONDS = 14 * 24 * 60 * 60
AUTH_COOKIE_NAME = "chatbot_factory_session"
REFRESH_COOKIE_NAME = "chatbot_factory_refresh"
REFRESH_COOKIE_PATH = "/auth"
ALLOWED_ROLES = {"admin", "manager", "end_user"}
WORKSPACE_READ_ONLY_DETAIL = "Admins have read-only access to projects and assistants."


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cookie_secure() -> bool:
    configured = os.getenv("AUTH_COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return ENVIRONMENT == "production"


def _cookie_samesite() -> str:
    configured = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
    if configured not in {"lax", "strict", "none"}:
        return "lax"
    return configured


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
    now = utc_now()
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=JWT_EXPIRES_SECONDS),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=JWT_EXPIRES_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )


def hash_refresh_token(token: str) -> str:
    secret = JWT_SECRET.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def create_refresh_session(db: Session, user: User) -> tuple[str, AuthSession]:
    raw_token = secrets.token_urlsafe(48)
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        created_at=utc_now(),
        expires_at=utc_now() + timedelta(seconds=REFRESH_TOKEN_EXPIRES_SECONDS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return raw_token, session


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_EXPIRES_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path=REFRESH_COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    clear_auth_cookie(response)
    clear_refresh_cookie(response)


def _invalid_refresh() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated")


def validate_refresh_session(db: Session, refresh_token: str | None) -> tuple[AuthSession, User]:
    if not refresh_token:
        raise _invalid_refresh()

    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == hash_refresh_token(refresh_token))
        .first()
    )
    now = utc_now()
    if (
        not session
        or session.revoked_at is not None
        or _as_aware_utc(session.expires_at) <= now
    ):
        raise _invalid_refresh()

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or user.status != "active":
        raise _invalid_refresh()

    return session, user


def rotate_refresh_session(db: Session, refresh_token: str | None) -> tuple[str, AuthSession, User]:
    session, user = validate_refresh_session(db, refresh_token)
    now = utc_now()
    new_raw_token = secrets.token_urlsafe(48)
    new_session = AuthSession(
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw_token),
        created_at=now,
        expires_at=now + timedelta(seconds=REFRESH_TOKEN_EXPIRES_SECONDS),
    )
    db.add(new_session)
    db.flush()

    session.revoked_at = now
    session.last_used_at = now
    session.replaced_by_session_id = new_session.id
    db.commit()
    db.refresh(new_session)
    return new_raw_token, new_session, user


def revoke_refresh_session(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return

    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == hash_refresh_token(refresh_token))
        .first()
    )
    if not session or session.revoked_at is not None:
        return

    now = utc_now()
    session.revoked_at = now
    session.last_used_at = now
    db.commit()


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


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


def ensure_workspace_write_access(current_user: User) -> User:
    if current_user.role != "manager":
        raise HTTPException(status_code=403, detail=WORKSPACE_READ_ONLY_DETAIL)
    return current_user


def require_workspace_manager(current_user: User = Depends(require_roles("admin", "manager"))) -> User:
    return ensure_workspace_write_access(current_user)
