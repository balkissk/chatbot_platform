import logging
from typing import Any

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.user import User

logger = logging.getLogger(__name__)

SENSITIVE_METADATA_KEYS = {
    "password",
    "password_hash",
    "access_token",
    "refresh_token",
    "api_key",
    "public_api_key",
    "secret",
    "client_secret",
    "llm_key",
}


def safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    result = {}
    for key, value in metadata.items():
        if key.lower() in SENSITIVE_METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
        elif isinstance(value, list):
            result[key] = [item for item in value if isinstance(item, (str, int, float, bool)) or item is None]
        elif isinstance(value, dict):
            result[key] = safe_metadata(value)
    return result


def record_audit_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    resource_name: str | None = None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        db.add(AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_name=actor.name if actor else None,
            actor_email=actor.email if actor else None,
            actor_role=actor.role if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            status=status,
            metadata_json=safe_metadata(metadata),
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist audit log")


def format_audit_action(action: str) -> str:
    return action.replace("_", " ").title()
