from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.user import User
from models.user_schema import (
    EmailVerificationResponse,
    RegistrationResponse,
    ResendVerificationRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserResponse,
    UserStatusUpdate,
)
from services.auth import (
    create_access_token,
    create_email_verification_token,
    get_current_user,
    get_db,
    hash_password,
    normalize_role,
    require_roles,
    send_verification_email,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def serialize_user(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at
    )


@router.post("/register", response_model=RegistrationResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    role = normalize_role(payload.role)
    if role == "admin":
        admin_exists = db.query(User).filter(User.role == "admin").first()
        if admin_exists:
            raise HTTPException(status_code=403, detail="Admin registration is closed")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
        status="active"
    )

    db.add(user)
    create_email_verification_token(user)
    db.commit()
    db.refresh(user)
    send_verification_email(user, user.email_verification_token)

    return RegistrationResponse(
        message="Account created. Please verify your email before signing in.",
        user=serialize_user(user)
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    if not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Please verify your email before signing in")

    return TokenResponse(
        access_token=create_access_token(user),
        user=serialize_user(user)
    )


@router.get("/verify-email", response_model=EmailVerificationResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    if (
        user.email_verification_expires_at
        and user.email_verification_expires_at < datetime.utcnow()
    ):
        raise HTTPException(status_code=400, detail="Verification token expired")

    user.email_verified_at = datetime.utcnow()
    user.email_verification_token = None
    user.email_verification_expires_at = None
    db.commit()

    return EmailVerificationResponse(message="Email verified. You can now sign in.")


@router.post("/resend-verification", response_model=EmailVerificationResponse)
def resend_verification(
    payload: ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        return EmailVerificationResponse(
            message="If the account exists, a verification email has been sent."
        )

    if user.email_verified_at:
        return EmailVerificationResponse(message="Email is already verified.")

    token = create_email_verification_token(user)
    db.commit()
    db.refresh(user)
    send_verification_email(user, token)

    return EmailVerificationResponse(
        message="If the account exists, a verification email has been sent."
    )


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

    user.name = name
    db.commit()
    db.refresh(user)

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

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    return {"message": "Password updated"}


@router.get("/users", response_model=list[UserResponse])
def list_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
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

    users = query.order_by(User.created_at.desc()).all()
    return [serialize_user(user) for user in users]


@router.post("/users", response_model=UserResponse)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=normalize_role(payload.role),
        status="active",
        email_verified_at=datetime.utcnow()
    )

    db.add(user)
    db.commit()
    db.refresh(user)

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

    user.status = status
    db.commit()
    db.refresh(user)

    return serialize_user(user)


def normalize_status(status: str) -> str:
    status = status.strip().lower()
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    return status
