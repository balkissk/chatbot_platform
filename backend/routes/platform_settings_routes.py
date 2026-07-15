from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.platform_settings import PlatformSettings
from models.platform_settings_schema import PlatformSettingsResponse, PlatformSettingsUpdate
from models.user import User
from services.audit import record_audit_log
from services.auth import require_roles

router = APIRouter(prefix="/admin/platform-settings", tags=["Platform Settings"])

DEFAULT_PLATFORM_SETTINGS = {
    "platform_name": "ChatBot Factory",
    "support_email": "support@chatbotfactory.com",
    "default_page_size": 10,
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_settings(db: Session, settings: PlatformSettings | None) -> PlatformSettingsResponse:
    if settings is None:
        return PlatformSettingsResponse(
            **DEFAULT_PLATFORM_SETTINGS,
            updated_at=None,
            updated_by=None,
            updated_by_name=None,
            updated_by_email=None,
        )

    updater = db.query(User).filter(User.id == settings.updated_by).first() if settings.updated_by else None
    return PlatformSettingsResponse(
        platform_name=settings.platform_name,
        support_email=settings.support_email,
        default_page_size=settings.default_page_size,
        updated_at=settings.updated_at,
        updated_by=settings.updated_by,
        updated_by_name=updater.name if updater else None,
        updated_by_email=updater.email if updater else None,
    )


def current_settings_record(db: Session) -> PlatformSettings | None:
    return db.query(PlatformSettings).order_by(PlatformSettings.id.asc()).first()


def editable_settings_record(db: Session) -> PlatformSettings:
    rows = db.query(PlatformSettings).order_by(PlatformSettings.id.asc()).all()
    if rows:
        record = rows[0]
        for duplicate in rows[1:]:
            db.delete(duplicate)
        return record

    record = PlatformSettings(id=1, **DEFAULT_PLATFORM_SETTINGS)
    db.add(record)
    return record


@router.get("", response_model=PlatformSettingsResponse)
def read_platform_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return serialize_settings(db, current_settings_record(db))


@router.put("", response_model=PlatformSettingsResponse)
def update_platform_settings(
    payload: PlatformSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    settings = editable_settings_record(db)
    previous = {
        "platform_name": settings.platform_name,
        "support_email": settings.support_email,
        "default_page_size": settings.default_page_size,
    }
    next_values = {
        "platform_name": payload.platform_name,
        "support_email": payload.support_email,
        "default_page_size": payload.default_page_size,
    }
    changed_fields = [
        key
        for key, value in next_values.items()
        if previous.get(key) != value
    ]

    settings.platform_name = payload.platform_name
    settings.support_email = payload.support_email
    settings.default_page_size = payload.default_page_size
    settings.updated_by = current_user.id

    db.commit()
    db.refresh(settings)

    if changed_fields:
        record_audit_log(
            db,
            actor=current_user,
            action="PLATFORM_SETTINGS_UPDATED",
            resource_type="platform_settings",
            resource_id=settings.id,
            resource_name=settings.platform_name,
            metadata={"changed_fields": changed_fields},
        )

    return serialize_settings(db, settings)
