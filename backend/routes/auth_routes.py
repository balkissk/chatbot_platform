from datetime import datetime, timedelta
from email.message import EmailMessage
import hashlib
import html as html_utils
import os
import secrets
import smtplib
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from models.chatbot import Chatbot
from models.project import Project
from models.user import User
from models.user_schema import (
    AdminUserCreate,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserListResponse,
    UserLogin,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserResponse,
    UserStatsResponse,
    UserStatusUpdate,
)
from config.settings import get_settings
from services.auth import (
    create_access_token,
    clear_auth_cookie,
    get_current_user,
    get_db,
    hash_password,
    normalize_role,
    require_roles,
    set_auth_cookie,
    verify_password,
)
from services.audit import record_audit_log

router = APIRouter(prefix="/auth", tags=["Auth"])
PASSWORD_RESET_RESPONSE = "If an account exists for that email, a password reset link has been sent."
PASSWORD_RESET_TOKEN_MINUTES = 60
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW_SECONDS = 60
FORGOT_PASSWORD_RATE_LIMIT = 3
FORGOT_PASSWORD_RATE_WINDOW_SECONDS = 5 * 60
_rate_limit_attempts: dict[tuple[str, str], list[float]] = {}
_rate_limit_time = time.monotonic


def _client_ip(request: Request | None) -> str:
    if request and request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_rate_limit(key: str, request: Request | None, limit: int, window_seconds: int) -> None:
    now = _rate_limit_time()
    bucket_key = (key, _client_ip(request))
    attempts = [
        timestamp
        for timestamp in _rate_limit_attempts.get(bucket_key, [])
        if now - timestamp < window_seconds
    ]
    if len(attempts) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    attempts.append(now)
    _rate_limit_attempts[bucket_key] = attempts


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def build_auth_email(
    *,
    title: str,
    body: str,
    cta_label: str,
    cta_url: str,
    security_note: str,
) -> tuple[str, str]:
    safe_title = html_utils.escape(title)
    safe_body = html_utils.escape(body)
    safe_cta_label = html_utils.escape(cta_label)
    safe_cta_url = html_utils.escape(cta_url, quote=True)
    safe_security_note = html_utils.escape(security_note)
    text = (
        "ChatBot Factory\n\n"
        f"{title}\n\n"
        f"{body}\n\n"
        f"{cta_label}: {cta_url}\n\n"
        f"This link expires in {PASSWORD_RESET_TOKEN_MINUTES} minutes.\n\n"
        f"{security_note}\n\n"
        "ChatBot Factory • Secure workspace access"
    )
    html_content = f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#eef5f6;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">Use the secure button to reset your ChatBot Factory password.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;background-color:#eef5f6;margin:0;padding:0;">
      <tr>
        <td align="center" style="padding:32px 12px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #d8e7ea;border-radius:14px;overflow:hidden;">
            <tr>
              <td align="center" style="padding:28px 24px 22px;background-color:#0f172a;">
                <div style="font-size:24px;line-height:1.2;font-weight:800;color:#ffffff;">ChatBot <span style="color:#2dd4bf;">Factory</span></div>
                <div style="margin-top:8px;font-size:12px;line-height:1.4;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:#a7f3d0;">Secure workspace access</div>
              </td>
            </tr>
            <tr>
              <td style="padding:34px 30px 30px;">
                <h1 style="margin:0 0 14px;font-size:26px;line-height:1.25;font-weight:800;color:#0f172a;">{safe_title}</h1>
                <p style="margin:0 0 26px;font-size:15px;line-height:1.65;color:#334155;">{safe_body}</p>
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 26px;">
                  <tr>
                    <td align="center" bgcolor="#0f766e" style="border-radius:10px;background-color:#0f766e;">
                      <a href="{safe_cta_url}" style="display:inline-block;padding:14px 24px;font-size:15px;line-height:1.2;font-weight:800;color:#ffffff;text-decoration:none;border-radius:10px;">{safe_cta_label}</a>
                    </td>
                  </tr>
                </table>
                <p style="margin:0 0 18px;font-size:14px;line-height:1.6;color:#475569;">This link expires in <strong style="color:#0f172a;">60 minutes</strong>.</p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;margin:0;">
                  <tr>
                    <td style="padding:14px 16px;background-color:#ecfeff;border-left:4px solid #0f766e;border-radius:8px;font-size:13px;line-height:1.55;color:#334155;">{safe_security_note}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:18px 24px;background-color:#f8fafc;border-top:1px solid #e2e8f0;font-size:13px;line-height:1.5;color:#64748b;">ChatBot Factory &bull; Secure workspace access</td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    return text, html_content


def send_auth_email(email: str, subject: str, text: str, html: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_from = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not smtp_host or not smtp_from:
        return

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        if use_tls:
            smtp.starttls()
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


def send_password_reset_email(email: str, reset_link: str) -> None:
    text, html = build_auth_email(
        title="Reset your password",
        body="We received a request to reset the password for your ChatBot Factory account. Use the secure button below to choose a new password.",
        cta_label="Reset Password",
        cta_url=reset_link,
        security_note="If you didn't request a password reset, you can safely ignore this email.",
    )
    send_auth_email(email, "Reset your ChatBot Factory password", text, html)


def send_account_setup_email(email: str, reset_link: str) -> None:
    text, html = build_auth_email(
        title="Set up your ChatBot Factory account",
        body="An administrator has created a ChatBot Factory account for you. Use the secure button below to set your password and access the platform.",
        cta_label="Set your password",
        cta_url=reset_link,
        security_note="If you did not expect this account invitation, you can safely ignore this email or contact your administrator.",
    )
    send_auth_email(email, "Welcome to ChatBot Factory - Set up your account", text, html)


def create_password_reset_link(user: User, db: Session) -> str:
    raw_token = secrets.token_urlsafe(32)
    user.password_reset_token = hash_reset_token(raw_token)
    user.password_reset_expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES)
    db.commit()
    return f"{get_settings().frontend_base_url}/reset-password?token={raw_token}"


def serialize_user(user: User, project_count: int | None = None, chatbot_count: int | None = None) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        project_count=project_count,
        chatbot_count=chatbot_count,
    )


def user_stats(db: Session) -> dict:
    return {
        "total_users": db.query(User.id).count(),
        "active_users": db.query(User.id).filter(User.status == "active").count(),
        "disabled_users": db.query(User.id).filter(User.status == "disabled").count(),
        "managers": db.query(User.id).filter(User.role == "manager").count(),
    }


def aggregate_user_counts(db: Session, user_ids: list[int]) -> dict[int, dict[str, int]]:
    if not user_ids:
        return {}

    project_rows = db.query(
        Project.user_id,
        func.count(Project.id),
    ).filter(
        Project.user_id.in_(user_ids)
    ).group_by(Project.user_id).all()

    chatbot_rows = db.query(
        Project.user_id,
        func.count(Chatbot.id),
    ).join(
        Chatbot,
        Chatbot.project_id == Project.id,
    ).filter(
        Project.user_id.in_(user_ids)
    ).group_by(Project.user_id).all()

    counts = {user_id: {"project_count": 0, "chatbot_count": 0} for user_id in user_ids}
    for user_id, count in project_rows:
        counts[user_id]["project_count"] = count
    for user_id, count in chatbot_rows:
        counts[user_id]["chatbot_count"] = count
    return counts


def serialize_users_with_counts(db: Session, users: list[User]) -> list[UserResponse]:
    counts = aggregate_user_counts(db, [user.id for user in users])
    return [
        serialize_user(
            user,
            project_count=counts.get(user.id, {}).get("project_count", 0),
            chatbot_count=counts.get(user.id, {}).get("chatbot_count", 0),
        )
        for user in users
    ]


def user_dependency_summary(db: Session, user_id: int) -> list[str]:
    dependencies: list[str] = []

    project_count = db.query(Project.id).filter(Project.user_id == user_id).count()
    if project_count:
        dependencies.append(f"{project_count} project(s)")

    rows = db.execute(
        text(
            """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.constraint_schema = kcu.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.constraint_schema = tc.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = 'users'
              AND ccu.column_name = 'id'
            """
        )
    ).fetchall()

    for table_name, column_name in rows:
        if table_name == "audit_logs" and column_name == "actor_user_id":
            continue
        count = db.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{column_name}" = :user_id'),
            {"user_id": user_id},
        ).scalar() or 0
        if count:
            dependencies.append(f"{count} {table_name} record(s)")

    return dependencies


@router.post("/login", response_model=TokenResponse)
def login(
    payload: UserLogin,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    _enforce_rate_limit("login", request, LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS)
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Your account has been disabled. Please contact an administrator.")

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    token = create_access_token(user)
    if response is not None:
        set_auth_cookie(response, token)

    return TokenResponse(user=serialize_user(user))


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "Logged out"}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, request: Request = None, db: Session = Depends(get_db)):
    _enforce_rate_limit(
        "forgot-password",
        request,
        FORGOT_PASSWORD_RATE_LIMIT,
        FORGOT_PASSWORD_RATE_WINDOW_SECONDS,
    )
    email = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if user and user.status == "active":
        reset_link = create_password_reset_link(user, db)
        try:
            send_password_reset_email(user.email, reset_link)
        except Exception:
            pass

    return {"message": PASSWORD_RESET_RESPONSE}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(payload.token)
    user = db.query(User).filter(User.password_reset_token == token_hash).first()

    if (
        not user
        or not user.password_reset_expires_at
        or user.password_reset_expires_at < datetime.utcnow()
        or user.status != "active"
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = hash_password(payload.new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    db.commit()

    record_audit_log(
        db,
        actor=user,
        action="PASSWORD_RESET",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.name,
    )

    return {"message": "Password reset successfully. You can now sign in."}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return serialize_user(current_user)


@router.put("/me", response_model=UserResponse)
def update_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    previous_name = user.name
    user.name = name
    db.commit()
    db.refresh(user)

    if previous_name != name:
        record_audit_log(
            db,
            actor=user,
            action="PROFILE_UPDATED",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.name,
            metadata={"changed_fields": ["name"]},
        )

    return serialize_user(user)


@router.put("/me/password")
def update_password(
    payload: UserPasswordUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    record_audit_log(
        db,
        actor=user,
        action="PASSWORD_CHANGED",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.name,
    )

    return {"message": "Password updated"}


@router.get("/users/stats", response_model=UserStatsResponse)
def get_user_stats(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    return user_stats(db)


@router.get("/users")
def list_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    query = db.query(User)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(User.name.ilike(term), User.email.ilike(term)))

    if role:
        query = query.filter(User.role == normalize_role(role))

    if status:
        status = normalize_status(status)
        query = query.filter(User.status == status)

    total = query.count()
    query = query.order_by(User.created_at.desc(), User.id.desc())

    if page is not None or page_size is not None:
        page = page or 1
        page_size = page_size or 10
        users = query.offset((page - 1) * page_size).limit(page_size).all()
        return UserListResponse(
            items=serialize_users_with_counts(db, users),
            total=total,
            page=page,
            page_size=page_size,
            stats=UserStatsResponse(**user_stats(db)),
        )

    users = query.all()
    return serialize_users_with_counts(db, users)


@router.post("/users", response_model=UserResponse)
def create_user(
    payload: AdminUserCreate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=normalize_role(payload.role),
        status="active",
        email_verified_at=datetime.utcnow()
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    reset_link = create_password_reset_link(user, db)
    try:
        send_account_setup_email(user.email, reset_link)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="User created, but setup email could not be sent") from exc

    record_audit_log(
        db,
        actor=current_user,
        action="USER_CREATED",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.name,
    )

    return serialize_user(user)


@router.put("/users/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    status = normalize_status(payload.status)
    if user.id == current_user.id and status != "active":
        raise HTTPException(status_code=400, detail="You cannot disable your own account")

    if user.role == "admin" and user.status == "active" and status != "active":
        active_admins = db.query(User).filter(
            User.role == "admin",
            User.status == "active"
        ).count()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="At least one active admin is required")

    previous_status = user.status
    user.status = status
    db.commit()
    db.refresh(user)

    if previous_status != status:
        record_audit_log(
            db,
            actor=current_user,
            action="USER_ACTIVATED" if status == "active" else "USER_DISABLED",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.name,
            metadata={"previous_status": previous_status, "status": status},
        )

    return serialize_user(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    dependencies = user_dependency_summary(db, user.id)
    if dependencies:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete this user because related data exists: {', '.join(dependencies)}."
        )

    db.delete(user)
    db.commit()

    return {"message": "User deleted"}


def normalize_status(status: str) -> str:
    status = status.strip().lower()
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    return status
