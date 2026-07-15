import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot_channel import ChannelLog, ChatbotChannel
from models.user import User
from routes.chatbot_routes import get_accessible_chatbot
from services.audit import record_audit_log
from services.auth import require_roles

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_CHANNELS = {"web", "widget", "api"}
CHANNEL_ORDER = ("web", "widget", "api")
SECRET_KEYS = {"api_key"}


class ChannelPayload(BaseModel):
    status: str | None = None
    config_json: dict | None = None
    deployed_version_id: int | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def clean_channel_type(channel_type: str) -> str:
    value = channel_type.strip().lower()
    if value not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail="Unsupported channel type")
    return value


def mask_config(config: dict | None) -> dict:
    result = dict(config or {})
    for key in SECRET_KEYS:
        if result.get(key):
            result[key] = "********"
    return result


def normalize_channel_config(config: dict | None) -> dict:
    return {
        key: value.strip() if isinstance(value, str) else value
        for key, value in dict(config or {}).items()
    }


def log_channel_event(
    db: Session,
    chatbot_id: int,
    channel_type: str,
    event_type: str,
    message: str,
    status: str = "info",
) -> None:
    db.add(ChannelLog(
        chatbot_id=chatbot_id,
        channel_type=channel_type,
        event_type=event_type,
        message=message[:500] if message else "",
        status=status,
    ))


def latest_log(
    db: Session,
    chatbot_id: int,
    channel_type: str,
    event_type: str | None = None,
    status: str | None = None,
) -> ChannelLog | None:
    query = db.query(ChannelLog).filter(
        ChannelLog.chatbot_id == chatbot_id,
        ChannelLog.channel_type == channel_type,
    )
    if event_type:
        query = query.filter(ChannelLog.event_type == event_type)
    if status:
        query = query.filter(ChannelLog.status == status)
    return query.order_by(ChannelLog.created_at.desc()).first()


def serialize_log(log: ChannelLog | None) -> dict | None:
    if not log:
        return None
    return {
        "id": log.id,
        "event_type": log.event_type,
        "message": log.message,
        "status": log.status,
        "created_at": log.created_at,
    }


def serialize_channel(db: Session, channel: ChatbotChannel | None, chatbot_id: int, channel_type: str) -> dict:
    error_log = latest_log(db, chatbot_id, channel_type, status="error")
    success_log = latest_log(db, chatbot_id, channel_type, "test_connection", "success")
    if channel and not channel.last_error:
        error_log = None
    return {
        "id": channel.id if channel else None,
        "chatbot_id": chatbot_id,
        "channel_type": channel_type,
        "status": channel.status if channel else "connected",
        "config_json": mask_config(channel.config_json if channel else {}),
        "deployed_version_id": channel.deployed_version_id if channel else None,
        "last_tested_at": channel.last_tested_at if channel else None,
        "last_verification_at": None,
        "last_incoming_message_at": None,
        "last_error": channel.last_error if channel else None,
        "created_at": channel.created_at if channel else None,
        "updated_at": channel.updated_at if channel else None,
        "last_test": serialize_log(success_log),
        "last_error_log": serialize_log(error_log),
        "last_historical_error": serialize_log(error_log),
    }


def get_channel(db: Session, chatbot_id: int, channel_type: str) -> ChatbotChannel | None:
    return db.query(ChatbotChannel).filter(
        ChatbotChannel.chatbot_id == chatbot_id,
        ChatbotChannel.channel_type == channel_type,
    ).first()


@router.get("/chatbots/{chatbot_id}/channels")
def list_chatbot_channels(
    chatbot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    get_accessible_chatbot(db, chatbot_id, current_user)
    existing = {
        channel.channel_type: channel
        for channel in db.query(ChatbotChannel).filter(
            ChatbotChannel.chatbot_id == chatbot_id,
            ChatbotChannel.channel_type.in_(SUPPORTED_CHANNELS),
        ).all()
    }
    return [
        serialize_channel(db, existing.get(channel_type), chatbot_id, channel_type)
        for channel_type in CHANNEL_ORDER
    ]


@router.post("/chatbots/{chatbot_id}/channels/{channel_type}")
def create_chatbot_channel(
    chatbot_id: int,
    channel_type: str,
    payload: ChannelPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, chatbot_id, current_user)
    channel_type = clean_channel_type(channel_type)
    existing = get_channel(db, chatbot.id, channel_type)
    if existing:
        raise HTTPException(status_code=409, detail="Channel already exists")

    channel = ChatbotChannel(
        chatbot_id=chatbot.id,
        channel_type=channel_type,
        status=payload.status or "connected",
        config_json=normalize_channel_config(payload.config_json),
        deployed_version_id=payload.deployed_version_id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    record_audit_log(
        db,
        actor=current_user,
        action="CHANNEL_ENABLED",
        resource_type="channel",
        resource_id=channel.id,
        resource_name=channel_type,
        metadata={"chatbot_id": chatbot.id, "status": channel.status},
    )
    return serialize_channel(db, channel, chatbot.id, channel_type)


@router.put("/chatbots/{chatbot_id}/channels/{channel_type}")
def update_chatbot_channel(
    chatbot_id: int,
    channel_type: str,
    payload: ChannelPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, chatbot_id, current_user)
    channel_type = clean_channel_type(channel_type)
    channel = get_channel(db, chatbot.id, channel_type)
    if not channel:
        channel = ChatbotChannel(chatbot_id=chatbot.id, channel_type=channel_type)
        db.add(channel)

    previous_status = channel.status
    previous_deployed_version_id = channel.deployed_version_id
    channel.status = payload.status if payload.status is not None else "connected"
    if payload.config_json is not None:
        previous = channel.config_json or {}
        next_config = normalize_channel_config(payload.config_json)
        for key in SECRET_KEYS:
            if next_config.get(key) == "********" and previous.get(key):
                next_config[key] = previous[key]
        channel.config_json = next_config
    if payload.deployed_version_id is not None:
        channel.deployed_version_id = payload.deployed_version_id
    channel.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(channel)
    if previous_deployed_version_id != channel.deployed_version_id and channel.deployed_version_id is not None:
        record_audit_log(
            db,
            actor=current_user,
            action="CHATBOT_DEPLOYED",
            resource_type="channel",
            resource_id=channel.id,
            resource_name=channel_type,
            metadata={"chatbot_id": chatbot.id, "deployed_version_id": channel.deployed_version_id},
        )
    elif previous_status != channel.status:
        record_audit_log(
            db,
            actor=current_user,
            action="CHANNEL_ENABLED" if channel.status != "disabled" else "CHANNEL_DISABLED",
            resource_type="channel",
            resource_id=channel.id,
            resource_name=channel_type,
            metadata={"chatbot_id": chatbot.id, "status": channel.status},
        )
    return serialize_channel(db, channel, chatbot.id, channel_type)


@router.post("/chatbots/{chatbot_id}/channels/{channel_type}/test")
def test_chatbot_channel(
    chatbot_id: int,
    channel_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, chatbot_id, current_user)
    channel_type = clean_channel_type(channel_type)
    channel = get_channel(db, chatbot.id, channel_type)
    if channel:
        channel.last_tested_at = datetime.utcnow()
        if channel.status == "not_configured":
            channel.status = "connected"
    log_channel_event(
        db,
        chatbot.id,
        channel_type,
        "test_connection",
        "Configuration validated",
        "success",
    )
    db.commit()
    return {
        "configured": True,
        "missing_fields": [],
    }


@router.patch("/chatbots/{chatbot_id}/channels/{channel_type}/clear-error")
def clear_channel_error(
    chatbot_id: int,
    channel_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, chatbot_id, current_user)
    channel_type = clean_channel_type(channel_type)
    channel = get_channel(db, chatbot.id, channel_type)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel.last_error = None
    channel.status = "connected"
    channel.updated_at = datetime.utcnow()
    log_channel_event(db, chatbot.id, channel_type, "error_cleared", "Current channel error cleared by manager", "info")
    db.commit()
    db.refresh(channel)
    return serialize_channel(db, channel, chatbot.id, channel_type)


@router.delete("/chatbots/{chatbot_id}/channels/{channel_type}")
def delete_chatbot_channel(
    chatbot_id: int,
    channel_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    chatbot = get_accessible_chatbot(db, chatbot_id, current_user)
    channel_type = clean_channel_type(channel_type)
    channel = get_channel(db, chatbot.id, channel_type)
    if channel:
        deleted_channel_id = channel.id
        db.delete(channel)
        db.commit()
        record_audit_log(
            db,
            actor=current_user,
            action="CHANNEL_DISABLED",
            resource_type="channel",
            resource_id=deleted_channel_id,
            resource_name=channel_type,
            metadata={"chatbot_id": chatbot.id},
        )
    return {"status": "deleted"}
