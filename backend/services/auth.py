import hashlib
import hmac
import os
import secrets
import smtplib
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.user import User


JWT_SECRET = os.getenv("JWT_SECRET", "0123456789abcdef0123456789abcdef")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_SECONDS = 60 * 60 * 24
EMAIL_VERIFICATION_EXPIRES_HOURS = 24
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:4200")
ALLOWED_ROLES = {"admin", "manager", "end_user"}
security = HTTPBearer()

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


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": int(time.time()) + JWT_EXPIRES_SECONDS
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_email_verification_token(user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.email_verification_token = token
    user.email_verification_expires_at = (
        datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_EXPIRES_HOURS)
    )
    return token


def send_verification_email(user: User, token: str) -> None:
    verification_url = f"{FRONTEND_URL}/verify-email?token={token}"
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_username or "no-reply@chatbot-platform.local")

    if not smtp_host:
        print(f"Email verification link for {user.email}: {verification_url}")
        return

    message = EmailMessage()
    message["Subject"] = "Verify your email"
    message["From"] = smtp_from
    message["To"] = user.email
    message.set_content(
        "Hello,\n\n"
        "Please verify your email address by opening this link:\n"
        f"{verification_url}\n\n"
        "This link expires in 24 hours."
    )

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_token(credentials.credentials)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()

    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Inactive or missing user")

    return user


def require_roles(*roles: str):
    allowed = set(roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return current_user

    return dependency
