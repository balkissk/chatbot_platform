from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.chatbot import Chatbot
from models.project import Project
from models.user import User
from models.user_schema import (
    RegistrationResponse,
    TokenResponse,
    UserCreate,
    UserListResponse,
    UserLogin,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserResponse,
    UserStatsResponse,
    UserStatusUpdate,
)
from services.auth import (
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    normalize_role,
    require_roles,
    verify_password,
)
from services.audit import record_audit_log

router = APIRouter(prefix="/auth", tags=["Auth"])


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
        status="active",
        email_verified_at=datetime.utcnow()
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return RegistrationResponse(
        message="Account created. You can now sign in.",
        user=serialize_user(user)
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user),
        user=serialize_user(user)
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


def normalize_status(status: str) -> str:
    status = status.strip().lower()
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    return status
