import time as time_module
from collections import Counter
from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, literal_column, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.admin_dashboard_schema import (
    AdminAuditLogsResponse,
    AdminAnalyticsResponse,
    AdminChatbotDetailsResponse,
    AdminChatbotsResponse,
    AdminChannelsResponse,
    AdminDashboardOverview,
    AdminRecentActivityResponse,
    AdminRuntimeLogsResponse,
    AdminSystemHealthResponse,
    AdminTopChatbot,
    AdminUsageResponse,
)
from models.audit_log import AuditLog
from models.chatbot import Chatbot
from models.chatbot_channel import ChannelLog, ChatbotChannel
from models.conversation import ConversationMessage, ConversationSession
from models.chunk import Chunk
from models.document import Document
from models.project import Project
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.audit import format_audit_action

router = APIRouter(prefix="/admin/analytics")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_session(db: Session, session: ConversationSession) -> dict:
    chatbot = db.query(Chatbot).filter(Chatbot.id == session.chatbot_id).first()
    project = db.query(Project).filter(Project.id == chatbot.project_id).first() if chatbot else None
    message_count = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).count()
    last_message = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).order_by(ConversationMessage.created_at.desc()).first()

    return {
        "id": session.id,
        "chatbot_id": session.chatbot_id,
        "chatbot_name": chatbot.name if chatbot else "Deleted chatbot",
        "project_id": project.id if project else None,
        "project_name": project.name if project else None,
        "version_id": session.version_id,
        "user_id": session.user_id,
        "channel": "dashboard" if session.user_id else "public",
        "current_node_key": session.current_node_key,
        "message_count": message_count,
        "last_message": last_message.content if last_message else "",
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def utc_now() -> datetime:
    return datetime.now(UTC)


def today_start_utc() -> datetime:
    return datetime.combine(utc_now().date(), time.min)


def month_start_utc() -> datetime:
    now = utc_now()
    return datetime(now.year, now.month, 1)


def count_query(db: Session, *entities):
    return db.query(func.count(*entities)).scalar() or 0


def session_channel(session: ConversationSession) -> str:
    variables = session.variables or {}
    channel = str(variables.get("__channel") or "").strip().lower()
    if channel in {"web", "public"}:
        return "public_chat"
    if channel in {"widget"}:
        return "widget"
    if channel in {"api", "rest_api"}:
        return "api"
    if channel in {"whatsapp", "messenger"}:
        return "legacy_other"
    if not channel:
        return "dashboard" if session.user_id else "public_chat"
    return "unknown"


def runtime_channel(channel: str | None) -> str:
    normalized = str(channel or "").strip().lower()
    if normalized in {"web", "public"}:
        return "public_chat"
    if normalized == "widget":
        return "widget"
    if normalized in {"api", "rest_api"}:
        return "api"
    if normalized in {"whatsapp", "messenger"}:
        return "legacy_other"
    return "unknown"


def runtime_channel_filter_values(channel: str) -> list[str]:
    normalized = runtime_channel(channel)
    if normalized == "public_chat":
        return ["web", "public", "public_chat"]
    if normalized == "widget":
        return ["widget"]
    if normalized == "api":
        return ["api", "rest_api"]
    if normalized == "legacy_other":
        return ["whatsapp", "messenger"]
    return [channel]


SUPPORTED_ANALYTICS_CHANNELS = {
    "public_chat": "Public Chat",
    "widget": "Web Widget",
    "api": "REST Public API",
}


def published_chatbot_count(db: Session) -> int:
    return db.query(VersionChatbot.chatbot_id).filter(
        VersionChatbot.status == "published"
    ).distinct().count()


def dashboard_usage(db: Session, days: int = 7) -> dict:
    bounded_days = max(1, min(days, 30))
    end_date = utc_now().date()
    start_date = end_date - timedelta(days=bounded_days - 1)
    start_dt = datetime.combine(start_date, time.min)

    rows = db.query(
        func.date(ConversationSession.created_at).label("day"),
        func.count(ConversationSession.id)
    ).filter(
        ConversationSession.created_at >= start_dt
    ).group_by(
        func.date(ConversationSession.created_at)
    ).all()

    counts = {str(day): count for day, count in rows}
    runtime_rows = db.query(
        func.date(RuntimeLog.created_at).label("day"),
        func.count(RuntimeLog.id)
    ).filter(
        RuntimeLog.created_at >= start_dt
    ).group_by(
        func.date(RuntimeLog.created_at)
    ).all()
    runtime_counts = {str(day): count for day, count in runtime_rows}
    total_runtime_logs = db.query(RuntimeLog.id).count()
    labels = [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(bounded_days)
    ]
    return {
        "labels": labels,
        "conversations": [counts.get(label, 0) for label in labels],
        "runtime_requests": (
            [runtime_counts.get(label, 0) for label in labels]
            if total_runtime_logs
            else None
        ),
    }


def dashboard_runtime_metrics(db: Session) -> dict:
    total_requests = db.query(RuntimeLog.id).count()
    if total_requests == 0:
        return {
            "total_requests": None,
            "successful_requests": None,
            "failed_requests": None,
            "success_rate": None,
            "average_response_time_ms": None,
            "rag_usage_rate": None,
        }

    successful_requests = db.query(RuntimeLog.id).filter(RuntimeLog.status == "success").count()
    failed_requests = db.query(RuntimeLog.id).filter(RuntimeLog.status == "failed").count()
    rag_requests = db.query(RuntimeLog.id).filter(RuntimeLog.rag_used.is_(True)).count()
    average_response_time = db.query(func.avg(RuntimeLog.response_time_ms)).filter(
        RuntimeLog.response_time_ms.isnot(None)
    ).scalar()

    return {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "success_rate": round((successful_requests / total_requests) * 100, 2),
        "average_response_time_ms": round(average_response_time) if average_response_time is not None else None,
        "rag_usage_rate": round((rag_requests / total_requests) * 100, 2),
    }


def dashboard_channels(db: Session) -> dict:
    sessions = db.query(
        ConversationSession.user_id,
        ConversationSession.variables
    ).all()
    counts = Counter({
        "public_chat": 0,
        "widget": 0,
        "api": 0,
        "legacy_other": 0,
        "unknown": 0,
    })
    for user_id, variables in sessions:
        fake_session = ConversationSession(user_id=user_id, variables=variables)
        normalized = session_channel(fake_session)
        if normalized == "dashboard":
            normalized = "unknown"
        counts[normalized if normalized in counts else "unknown"] += 1
    return {
        "public_chat": counts["public_chat"],
        "widget": counts["widget"],
        "api": counts["api"],
        "legacy_other": counts["legacy_other"],
        "unknown": counts["unknown"],
    }


def top_chatbots_rows(db: Session, limit: int = 5) -> list[dict]:
    bounded_limit = max(1, min(limit, 50))
    Owner = aliased(User)
    ActiveVersion = aliased(VersionChatbot)
    PublishedVersion = aliased(VersionChatbot)

    latest_published = db.query(
        VersionChatbot.chatbot_id.label("chatbot_id"),
        func.max(VersionChatbot.version_number).label("version_number")
    ).filter(
        VersionChatbot.status == "published"
    ).group_by(
        VersionChatbot.chatbot_id
    ).subquery()

    rows = db.query(
        Chatbot.id.label("chatbot_id"),
        Chatbot.name.label("chatbot_name"),
        Chatbot.is_active.label("is_active"),
        Project.id.label("project_id"),
        Project.name.label("project_name"),
        Owner.id.label("owner_id"),
        Owner.name.label("owner_name"),
        Owner.email.label("owner_email"),
        func.count(ConversationSession.id).label("conversation_count"),
        func.coalesce(ActiveVersion.id, PublishedVersion.id).label("published_version_id"),
        func.coalesce(ActiveVersion.version_number, PublishedVersion.version_number).label("published_version_number"),
    ).outerjoin(
        Project,
        Project.id == Chatbot.project_id
    ).outerjoin(
        Owner,
        Owner.id == Project.user_id
    ).outerjoin(
        ConversationSession,
        ConversationSession.chatbot_id == Chatbot.id
    ).outerjoin(
        ActiveVersion,
        and_(
            ActiveVersion.id == Chatbot.active_version_id,
            ActiveVersion.status == "published",
        )
    ).outerjoin(
        latest_published,
        latest_published.c.chatbot_id == Chatbot.id
    ).outerjoin(
        PublishedVersion,
        and_(
            PublishedVersion.chatbot_id == latest_published.c.chatbot_id,
            PublishedVersion.version_number == latest_published.c.version_number,
            PublishedVersion.status == "published",
        )
    ).group_by(
        Chatbot.id,
        Chatbot.name,
        Chatbot.is_active,
        Project.id,
        Project.name,
        Owner.id,
        Owner.name,
        Owner.email,
        ActiveVersion.id,
        ActiveVersion.version_number,
        PublishedVersion.id,
        PublishedVersion.version_number,
    ).order_by(
        func.count(ConversationSession.id).desc(),
        Chatbot.id.asc(),
    ).limit(bounded_limit).all()

    return [
        {
            "chatbot_id": row.chatbot_id,
            "chatbot_name": row.chatbot_name,
            "owner_id": row.owner_id,
            "owner_name": row.owner_name,
            "owner_email": row.owner_email,
            "project_id": row.project_id,
            "project_name": row.project_name,
            "conversation_count": row.conversation_count,
            "published_version_id": row.published_version_id,
            "published_version_label": (
                f"v{row.published_version_number}"
                if row.published_version_number is not None
                else None
            ),
            "status": "active" if row.is_active else "disabled",
        }
        for row in rows
    ]


def analytics_period_bounds(period: str) -> tuple[str, int, datetime, datetime]:
    normalized = (period or "30d").strip().lower()
    days_by_period = {"7d": 7, "30d": 30, "90d": 90}
    if normalized not in days_by_period:
        raise HTTPException(status_code=400, detail="Unsupported analytics range")

    days = days_by_period[normalized]
    end_date = utc_now().date()
    start_date = end_date - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)
    return normalized, days, start_dt, end_dt


def analytics_labels(start_dt: datetime, days: int) -> list[str]:
    start_date = start_dt.date()
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(days)
    ]


def analytics_conversation_series(db: Session, start_dt: datetime, end_dt: datetime, labels: list[str]) -> dict:
    rows = db.query(
        func.date(ConversationSession.created_at).label("day"),
        func.count(ConversationSession.id).label("count"),
    ).filter(
        ConversationSession.created_at >= start_dt,
        ConversationSession.created_at < end_dt,
    ).group_by(
        func.date(ConversationSession.created_at)
    ).all()
    counts = {str(day): count for day, count in rows}
    return {
        "labels": labels,
        "conversations": [counts.get(label, 0) for label in labels],
    }


def analytics_runtime_series(db: Session, start_dt: datetime, end_dt: datetime, labels: list[str]) -> dict:
    rows = db.query(
        func.date(RuntimeLog.created_at).label("day"),
        RuntimeLog.status.label("status"),
        func.count(RuntimeLog.id).label("count"),
    ).filter(
        RuntimeLog.created_at >= start_dt,
        RuntimeLog.created_at < end_dt,
    ).group_by(
        func.date(RuntimeLog.created_at),
        RuntimeLog.status,
    ).all()

    success_counts = {label: 0 for label in labels}
    failed_counts = {label: 0 for label in labels}
    total_counts = {label: 0 for label in labels}
    for day, status, count in rows:
        key = str(day)
        if key not in total_counts:
            continue
        total_counts[key] += count
        if status == "success":
            success_counts[key] += count
        elif status == "failed":
            failed_counts[key] += count

    return {
        "labels": labels,
        "successful_requests": [success_counts[label] for label in labels],
        "failed_requests": [failed_counts[label] for label in labels],
        "total_requests": [total_counts[label] for label in labels],
    }


def analytics_runtime_metrics(db: Session, start_dt: datetime, end_dt: datetime) -> dict:
    total_requests = db.query(RuntimeLog.id).filter(
        RuntimeLog.created_at >= start_dt,
        RuntimeLog.created_at < end_dt,
    ).count()
    successful_requests = db.query(RuntimeLog.id).filter(
        RuntimeLog.created_at >= start_dt,
        RuntimeLog.created_at < end_dt,
        RuntimeLog.status == "success",
    ).count()
    failed_requests = db.query(RuntimeLog.id).filter(
        RuntimeLog.created_at >= start_dt,
        RuntimeLog.created_at < end_dt,
        RuntimeLog.status == "failed",
    ).count()
    average_response_time = db.query(func.avg(RuntimeLog.response_time_ms)).filter(
        RuntimeLog.created_at >= start_dt,
        RuntimeLog.created_at < end_dt,
        RuntimeLog.response_time_ms.isnot(None),
    ).scalar()
    success_rate = round((successful_requests / total_requests) * 100, 2) if total_requests else None
    return {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "success_rate": success_rate,
        "average_response_time_ms": round(average_response_time) if average_response_time is not None else None,
    }


def analytics_channel_usage(db: Session, start_dt: datetime, end_dt: datetime) -> tuple[list[dict], int]:
    conversation_rows = db.query(
        ConversationSession.user_id,
        ConversationSession.variables,
    ).filter(
        ConversationSession.created_at >= start_dt,
        ConversationSession.created_at < end_dt,
    ).all()
    runtime_rows = db.query(
        RuntimeLog.channel,
        func.count(RuntimeLog.id).label("count"),
    ).filter(
        RuntimeLog.created_at >= start_dt,
        RuntimeLog.created_at < end_dt,
    ).group_by(
        RuntimeLog.channel
    ).all()

    conversations = Counter({"public_chat": 0, "widget": 0, "api": 0})
    runtime_requests = Counter({"public_chat": 0, "widget": 0, "api": 0})
    legacy_excluded = 0

    for user_id, variables in conversation_rows:
        normalized = session_channel(ConversationSession(user_id=user_id, variables=variables))
        if normalized == "dashboard":
            normalized = "unknown"
        if normalized in SUPPORTED_ANALYTICS_CHANNELS:
            conversations[normalized] += 1
        elif normalized == "legacy_other":
            legacy_excluded += 1

    for channel, count in runtime_rows:
        normalized = runtime_channel(channel)
        if normalized in SUPPORTED_ANALYTICS_CHANNELS:
            runtime_requests[normalized] += count
        elif normalized == "legacy_other":
            legacy_excluded += count

    return [
        {
            "channel": channel,
            "label": label,
            "conversations": conversations[channel],
            "runtime_requests": runtime_requests[channel],
        }
        for channel, label in SUPPORTED_ANALYTICS_CHANNELS.items()
    ], legacy_excluded


def analytics_top_chatbot_usage(db: Session, start_dt: datetime, end_dt: datetime, limit: int = 5) -> list[dict]:
    bounded_limit = max(1, min(limit, 20))
    Owner = aliased(User)
    PublishedVersion = aliased(VersionChatbot)

    latest_published = db.query(
        VersionChatbot.chatbot_id.label("chatbot_id"),
        func.max(VersionChatbot.version_number).label("version_number"),
    ).filter(
        VersionChatbot.status == "published"
    ).group_by(
        VersionChatbot.chatbot_id
    ).subquery()

    rows = db.query(
        Chatbot.id.label("chatbot_id"),
        Chatbot.name.label("chatbot_name"),
        Chatbot.is_active.label("is_active"),
        Project.id.label("project_id"),
        Project.name.label("project_name"),
        Owner.id.label("owner_id"),
        Owner.name.label("owner_name"),
        Owner.email.label("owner_email"),
        PublishedVersion.id.label("published_version_id"),
        func.count(func.distinct(ConversationSession.id)).label("conversations"),
    ).join(
        ConversationSession,
        ConversationSession.chatbot_id == Chatbot.id,
    ).outerjoin(
        Project,
        Project.id == Chatbot.project_id,
    ).outerjoin(
        Owner,
        Owner.id == Project.user_id,
    ).outerjoin(
        latest_published,
        latest_published.c.chatbot_id == Chatbot.id,
    ).outerjoin(
        PublishedVersion,
        and_(
            PublishedVersion.chatbot_id == latest_published.c.chatbot_id,
            PublishedVersion.version_number == latest_published.c.version_number,
            PublishedVersion.status == "published",
        ),
    ).filter(
        ConversationSession.created_at >= start_dt,
        ConversationSession.created_at < end_dt,
    ).group_by(
        Chatbot.id,
        Chatbot.name,
        Chatbot.is_active,
        Project.id,
        Project.name,
        Owner.id,
        Owner.name,
        Owner.email,
        PublishedVersion.id,
    ).order_by(
        func.count(func.distinct(ConversationSession.id)).desc(),
        Chatbot.id.asc(),
    ).limit(bounded_limit).all()

    items = []
    for row in rows:
        if not row.is_active:
            publication_status = "disabled"
        elif row.published_version_id:
            publication_status = "published"
        else:
            publication_status = "draft_only"
        items.append({
            "chatbot_id": row.chatbot_id,
            "chatbot_name": row.chatbot_name,
            "owner_id": row.owner_id,
            "owner_name": row.owner_name,
            "owner_email": row.owner_email,
            "project_id": row.project_id,
            "project_name": row.project_name,
            "conversations": row.conversations,
            "publication_status": publication_status,
        })
    return items


def platform_analytics_payload(db: Session, period: str = "30d") -> dict:
    normalized_period, days, start_dt, end_dt = analytics_period_bounds(period)
    labels = analytics_labels(start_dt, days)
    conversations = analytics_conversation_series(db, start_dt, end_dt, labels)
    runtime_series = analytics_runtime_series(db, start_dt, end_dt, labels)
    runtime = analytics_runtime_metrics(db, start_dt, end_dt)
    channel_usage, legacy_excluded = analytics_channel_usage(db, start_dt, end_dt)
    total_conversations = sum(conversations["conversations"])

    return {
        "period": normalized_period,
        "days": days,
        "start_date": start_dt,
        "end_date": end_dt,
        "kpis": {
            "total_conversations": total_conversations,
            "runtime_requests": runtime["total_requests"],
            "runtime_success_rate": runtime["success_rate"],
            "average_response_time_ms": runtime["average_response_time_ms"],
        },
        "conversations_over_time": conversations,
        "runtime_requests_over_time": runtime_series,
        "channel_usage": channel_usage,
        "top_chatbots": analytics_top_chatbot_usage(db, start_dt, end_dt, 5),
        "runtime_performance": runtime,
        "legacy_channels_excluded": legacy_excluded,
    }


DEPLOYED_CHANNEL_STATUSES = {"connected", "configured", "verified", "deployed"}


def admin_chatbot_stats(db: Session) -> dict:
    published_ids = select(VersionChatbot.chatbot_id).filter(
        VersionChatbot.status == "published"
    ).distinct()

    total = db.query(Chatbot.id).count()
    disabled = db.query(Chatbot.id).filter(Chatbot.is_active.is_(False)).count()
    published = db.query(Chatbot.id).filter(
        Chatbot.is_active.is_(True),
        Chatbot.id.in_(published_ids),
    ).count()
    draft_only = db.query(Chatbot.id).filter(
        Chatbot.is_active.is_(True),
        ~Chatbot.id.in_(published_ids),
    ).count()

    return {
        "total": total,
        "published": published,
        "draft_only": draft_only,
        "disabled": disabled,
    }


def admin_chatbot_base_query(db: Session):
    Owner = aliased(User)
    LatestVersion = aliased(VersionChatbot)
    PublishedVersion = aliased(VersionChatbot)

    version_counts = db.query(
        VersionChatbot.chatbot_id.label("chatbot_id"),
        func.count(VersionChatbot.id).label("versions_count"),
    ).group_by(
        VersionChatbot.chatbot_id
    ).subquery()

    latest_version_numbers = db.query(
        VersionChatbot.chatbot_id.label("chatbot_id"),
        func.max(VersionChatbot.version_number).label("version_number"),
    ).group_by(
        VersionChatbot.chatbot_id
    ).subquery()

    latest_published_numbers = db.query(
        VersionChatbot.chatbot_id.label("chatbot_id"),
        func.max(VersionChatbot.version_number).label("version_number"),
    ).filter(
        VersionChatbot.status == "published"
    ).group_by(
        VersionChatbot.chatbot_id
    ).subquery()

    conversation_summary = db.query(
        ConversationSession.chatbot_id.label("chatbot_id"),
        func.count(ConversationSession.id).label("conversations_count"),
        func.max(ConversationSession.updated_at).label("last_activity_at"),
    ).group_by(
        ConversationSession.chatbot_id
    ).subquery()

    runtime_summary = db.query(
        RuntimeLog.chatbot_id.label("chatbot_id"),
        func.count(RuntimeLog.id).label("runtime_request_count"),
        func.max(RuntimeLog.created_at).label("last_runtime_at"),
    ).group_by(
        RuntimeLog.chatbot_id
    ).subquery()

    channel_summary = db.query(
        ChatbotChannel.chatbot_id.label("chatbot_id"),
        func.sum(
            case(
                (
                    or_(
                        ChatbotChannel.status.in_(DEPLOYED_CHANNEL_STATUSES),
                        ChatbotChannel.deployed_version_id.isnot(None),
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("deployed_channel_count"),
    ).group_by(
        ChatbotChannel.chatbot_id
    ).subquery()

    return db.query(
        Chatbot.id.label("chatbot_id"),
        Chatbot.name.label("chatbot_name"),
        Chatbot.description.label("description"),
        Chatbot.language.label("language"),
        Chatbot.channel.label("channel"),
        Chatbot.build_method.label("build_method"),
        Chatbot.is_active.label("is_active"),
        Chatbot.created_at.label("created_at"),
        Project.id.label("project_id"),
        Project.name.label("project_name"),
        Owner.id.label("owner_id"),
        Owner.name.label("owner_name"),
        Owner.email.label("owner_email"),
        func.coalesce(version_counts.c.versions_count, 0).label("versions_count"),
        LatestVersion.id.label("latest_version_id"),
        LatestVersion.version_number.label("latest_version_number"),
        PublishedVersion.id.label("published_version_id"),
        PublishedVersion.version_number.label("published_version_number"),
        func.coalesce(conversation_summary.c.conversations_count, 0).label("conversations_count"),
        conversation_summary.c.last_activity_at.label("last_activity_at"),
        func.coalesce(runtime_summary.c.runtime_request_count, 0).label("runtime_request_count"),
        runtime_summary.c.last_runtime_at.label("last_runtime_at"),
        func.coalesce(channel_summary.c.deployed_channel_count, 0).label("deployed_channel_count"),
    ).outerjoin(
        Project,
        Project.id == Chatbot.project_id,
    ).outerjoin(
        Owner,
        Owner.id == Project.user_id,
    ).outerjoin(
        version_counts,
        version_counts.c.chatbot_id == Chatbot.id,
    ).outerjoin(
        latest_version_numbers,
        latest_version_numbers.c.chatbot_id == Chatbot.id,
    ).outerjoin(
        LatestVersion,
        and_(
            LatestVersion.chatbot_id == latest_version_numbers.c.chatbot_id,
            LatestVersion.version_number == latest_version_numbers.c.version_number,
        ),
    ).outerjoin(
        latest_published_numbers,
        latest_published_numbers.c.chatbot_id == Chatbot.id,
    ).outerjoin(
        PublishedVersion,
        and_(
            PublishedVersion.chatbot_id == latest_published_numbers.c.chatbot_id,
            PublishedVersion.version_number == latest_published_numbers.c.version_number,
            PublishedVersion.status == "published",
        ),
    ).outerjoin(
        conversation_summary,
        conversation_summary.c.chatbot_id == Chatbot.id,
    ).outerjoin(
        runtime_summary,
        runtime_summary.c.chatbot_id == Chatbot.id,
    ).outerjoin(
        channel_summary,
        channel_summary.c.chatbot_id == Chatbot.id,
    )


def apply_admin_chatbot_filters(
    db: Session,
    query,
    search: str | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
    publication_status: str | None = None,
    deployment_status: str | None = None,
):
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(Chatbot.name.ilike(term))
    if owner_id:
        query = query.filter(Project.user_id == owner_id)
    if project_id:
        query = query.filter(Project.id == project_id)

    normalized_publication = (publication_status or "").strip().lower()
    published_ids = select(VersionChatbot.chatbot_id).filter(
        VersionChatbot.status == "published"
    ).distinct()
    if normalized_publication == "published":
        query = query.filter(Chatbot.is_active.is_(True), Chatbot.id.in_(published_ids))
    elif normalized_publication in {"draft", "draft_only"}:
        query = query.filter(Chatbot.is_active.is_(True), ~Chatbot.id.in_(published_ids))
    elif normalized_publication == "disabled":
        query = query.filter(Chatbot.is_active.is_(False))

    normalized_deployment = (deployment_status or "").strip().lower()
    deployed_ids = select(ChatbotChannel.chatbot_id).filter(
        or_(
            ChatbotChannel.status.in_(DEPLOYED_CHANNEL_STATUSES),
            ChatbotChannel.deployed_version_id.isnot(None),
        )
    ).distinct()
    if normalized_deployment == "deployed":
        query = query.filter(Chatbot.id.in_(deployed_ids))
    elif normalized_deployment in {"not_deployed", "not deployed"}:
        query = query.filter(~Chatbot.id.in_(deployed_ids))

    return query


def apply_admin_chatbot_sort(query, sort_by: str, sort_order: str):
    descending = sort_order.lower() != "asc"
    columns = {
        "created_at": literal_column("created_at"),
        "name": literal_column("chatbot_name"),
        "owner": literal_column("owner_name"),
        "project": literal_column("project_name"),
        "conversations": literal_column("conversations_count"),
        "last_activity": literal_column("last_activity_at"),
        "last_runtime": literal_column("last_runtime_at"),
    }
    column = columns.get(sort_by, columns["created_at"])
    return query.order_by(column.desc().nullslast() if descending else column.asc().nullslast(), literal_column("chatbot_id").asc())


def enabled_channels_for_chatbots(db: Session, chatbot_ids: list[int]) -> dict[int, list[str]]:
    channels = {chatbot_id: [] for chatbot_id in chatbot_ids}
    if not chatbot_ids:
        return channels

    rows = db.query(
        ChatbotChannel.chatbot_id,
        ChatbotChannel.channel_type,
    ).filter(
        ChatbotChannel.chatbot_id.in_(chatbot_ids),
        or_(
            ChatbotChannel.status.in_(DEPLOYED_CHANNEL_STATUSES),
            ChatbotChannel.deployed_version_id.isnot(None),
        ),
    ).order_by(
        ChatbotChannel.chatbot_id.asc(),
        ChatbotChannel.channel_type.asc(),
    ).all()

    for chatbot_id, channel_type in rows:
        channels.setdefault(chatbot_id, []).append(channel_type)
    return channels


def serialize_admin_chatbot_row(row, enabled_channels: list[str], include_details: bool = False) -> dict:
    disabled = not bool(row.is_active)
    if disabled:
        publication_status = "disabled"
    elif row.published_version_id:
        publication_status = "published"
    else:
        publication_status = "draft_only"

    payload = {
        "chatbot_id": row.chatbot_id,
        "chatbot_name": row.chatbot_name,
        "owner_id": row.owner_id,
        "owner_name": row.owner_name,
        "owner_email": row.owner_email,
        "project_id": row.project_id,
        "project_name": row.project_name,
        "created_at": row.created_at,
        "versions_count": row.versions_count,
        "latest_version_id": row.latest_version_id,
        "latest_version_label": f"v{row.latest_version_number}" if row.latest_version_number is not None else None,
        "published_version_id": row.published_version_id,
        "published_version_label": f"v{row.published_version_number}" if row.published_version_number is not None else None,
        "conversations_count": row.conversations_count,
        "runtime_request_count": row.runtime_request_count,
        "last_activity_at": row.last_activity_at,
        "last_runtime_at": row.last_runtime_at,
        "publication_status": publication_status,
        "deployment_status": "deployed" if row.deployed_channel_count else "not_deployed",
        "disabled": disabled,
        "enabled_channels": enabled_channels,
    }
    if include_details:
        payload.update({
            "description": row.description,
            "language": row.language,
            "channel": row.channel,
            "build_method": row.build_method,
            "updated_at": None,
        })
    return payload


def admin_chatbot_list_payload(
    db: Session,
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    owner_id: int | None = None,
    project_id: int | None = None,
    publication_status: str | None = None,
    deployment_status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    bounded_page = max(page, 1)
    bounded_page_size = max(1, min(page_size, 100))

    query = apply_admin_chatbot_filters(
        db,
        admin_chatbot_base_query(db),
        search=search,
        owner_id=owner_id,
        project_id=project_id,
        publication_status=publication_status,
        deployment_status=deployment_status,
    )
    total = query.count()
    rows = apply_admin_chatbot_sort(query, sort_by, sort_order).offset(
        (bounded_page - 1) * bounded_page_size
    ).limit(
        bounded_page_size
    ).all()
    channels = enabled_channels_for_chatbots(db, [row.chatbot_id for row in rows])

    return {
        "items": [
            serialize_admin_chatbot_row(row, channels.get(row.chatbot_id, []))
            for row in rows
        ],
        "total": total,
        "page": bounded_page,
        "page_size": bounded_page_size,
        "total_pages": (total + bounded_page_size - 1) // bounded_page_size if total else 0,
        "stats": admin_chatbot_stats(db),
    }


def recent_activity(db: Session, limit: int = 10) -> dict:
    bounded_limit = max(1, min(limit, 50))
    try:
        rows = db.query(AuditLog).order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        ).limit(bounded_limit).all()
    except SQLAlchemyError:
        db.rollback()
        rows = []

    return {
        "source": "audit_logs",
        "items": [
            {
                "id": row.id,
                "created_at": row.created_at,
                "actor_id": row.actor_user_id,
                "actor_name": row.actor_name,
                "actor_email": row.actor_email,
                "actor_role": row.actor_role,
                "action": format_audit_action(row.action),
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "resource_name": row.resource_name,
                "status": row.status,
                "details": None,
            }
            for row in rows
        ],
    }


def system_health(db: Session) -> dict:
    checked_at = utc_now()
    db_started = time_module.perf_counter()
    try:
        db.execute(text("SELECT 1")).scalar()
        database_status = {
            "status": "healthy",
            "response_time_ms": round((time_module.perf_counter() - db_started) * 1000),
            "message": "Database query succeeded",
        }
    except Exception:
        database_status = {
            "status": "offline",
            "response_time_ms": None,
            "message": "Database health query failed",
        }

    runtime_service = runtime_health_service(db)

    return {
        "checked_at": checked_at,
        "services": {
            "backend_api": {
                "status": "healthy",
                "response_time_ms": 0,
                "message": "Dashboard endpoint executed",
            },
            "database": database_status,
            "runtime": runtime_service,
            "embedding_service": {
                "status": "not_monitored",
                "response_time_ms": None,
                "message": "No safe persisted embedding health check exists",
            },
            "llm_provider": {
                "status": "not_monitored",
                "response_time_ms": None,
                "message": "External provider checks are not called from dashboard",
            },
            "storage": {
                "status": "not_monitored",
                "response_time_ms": None,
                "message": "No storage health check is persisted",
            },
        },
    }


def runtime_health_service(db: Session) -> dict:
    last_success = db.query(RuntimeLog).filter(
        RuntimeLog.status == "success"
    ).order_by(RuntimeLog.created_at.desc()).first()
    last_failure = db.query(RuntimeLog).filter(
        RuntimeLog.status == "failed"
    ).order_by(RuntimeLog.created_at.desc()).first()
    if not last_success and not last_failure:
        return {
            "status": "not_monitored",
            "response_time_ms": None,
            "message": "No runtime executions have been logged yet",
            "last_success_at": None,
            "last_failure_at": None,
            "failures_last_24h": None,
            "success_rate_last_24h": None,
        }

    since = utc_now().replace(tzinfo=None) - timedelta(hours=24)
    recent_total = db.query(RuntimeLog.id).filter(RuntimeLog.created_at >= since).count()
    recent_success = db.query(RuntimeLog.id).filter(
        RuntimeLog.created_at >= since,
        RuntimeLog.status == "success",
    ).count()
    recent_failures = db.query(RuntimeLog.id).filter(
        RuntimeLog.created_at >= since,
        RuntimeLog.status == "failed",
    ).count()
    success_rate = round((recent_success / recent_total) * 100, 2) if recent_total else None
    latest = db.query(RuntimeLog).order_by(RuntimeLog.created_at.desc()).first()

    if recent_total == 0:
        status = "warning"
        message = "Runtime is logged, but no executions occurred in the last 24 hours"
    elif latest and latest.status == "failed":
        status = "warning"
        message = "Most recent runtime execution failed"
    elif success_rate is not None and success_rate < 80:
        status = "warning"
        message = "Runtime failure rate is elevated in the last 24 hours"
    else:
        status = "healthy"
        message = "Recent runtime executions are succeeding"

    return {
        "status": status,
        "response_time_ms": latest.response_time_ms if latest else None,
        "message": message,
        "last_success_at": last_success.created_at if last_success else None,
        "last_failure_at": last_failure.created_at if last_failure else None,
        "failures_last_24h": recent_failures,
        "success_rate_last_24h": success_rate,
    }


def dashboard_overview_payload(db: Session) -> dict:
    today_start = today_start_utc()
    month_start = month_start_utc()

    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.status == "active").count()
    disabled_users = db.query(User).filter(User.status != "active").count()
    active_managers = db.query(User).filter(User.role == "manager", User.status == "active").count()
    new_this_month = db.query(User).filter(User.created_at >= month_start).count()

    total_projects = db.query(Project).count()
    total_chatbots = db.query(Chatbot).count()
    active_chatbots = db.query(Chatbot).filter(Chatbot.is_active.is_(True)).count()
    disabled_chatbots = db.query(Chatbot).filter(Chatbot.is_active.is_(False)).count()
    published_chatbots = published_chatbot_count(db)
    draft_chatbots = max(total_chatbots - published_chatbots, 0)
    published_versions = db.query(VersionChatbot).filter(VersionChatbot.status == "published").count()

    total_sessions = db.query(ConversationSession).count()
    total_messages = db.query(ConversationMessage).count()
    sessions_today = db.query(ConversationSession).filter(ConversationSession.created_at >= today_start).count()
    messages_today = db.query(ConversationMessage).filter(ConversationMessage.created_at >= today_start).count()

    total_documents = db.query(Document).count()
    processing_documents = db.query(Document).filter(Document.status.in_(["processing", "uploaded"])).count()
    ready_documents = db.query(Document).filter(Document.status.in_(["processed", "ready"])).count()
    failed_documents = db.query(Document).filter(Document.status == "failed").count()
    total_chunks = db.query(Chunk).count()
    total_embeddings = db.query(Chunk).filter(
        (Chunk.embedding_status == "ready") | Chunk.embedding.isnot(None)
    ).count()

    top_chatbots = top_chatbots_rows(db, 5)
    recent = recent_activity(db, 8)
    usage = dashboard_usage(db, 7)
    channels = dashboard_channels(db)
    health = system_health(db)

    runtime = dashboard_runtime_metrics(db)

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "disabled": disabled_users,
            "active_managers": active_managers,
            "new_this_month": new_this_month,
        },
        "projects": {
            "total": total_projects,
            "active": None,
            "disabled": None,
        },
        "chatbots": {
            "total": total_chatbots,
            "published": published_chatbots,
            "draft": draft_chatbots,
            "active": active_chatbots,
            "disabled": disabled_chatbots,
        },
        "conversations": {
            "total": total_sessions,
            "today": sessions_today,
            "total_messages": total_messages,
            "messages_today": messages_today,
        },
        "runtime": runtime,
        "knowledge_base": {
            "total_documents": total_documents,
            "processing_documents": processing_documents,
            "ready_documents": ready_documents,
            "failed_documents": failed_documents,
            "total_chunks": total_chunks,
            "total_embeddings": total_embeddings,
        },
        "usage": usage,
        "channels": channels,
        "top_chatbots": top_chatbots,
        "recent_activity": recent,
        "system_health": health,
        "total_users": total_users,
        "active_users": active_users,
        "disabled_users": disabled_users,
        "active_managers": active_managers,
        "new_users": new_this_month,
        "total_projects": total_projects,
        "total_chatbots": total_chatbots,
        "active_chatbots": active_chatbots,
        "published_versions": published_chatbots,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "sessions_today": sessions_today,
        "messages_today": messages_today,
        "runtime_success_rate": runtime["success_rate"],
        "failed_runtime_requests": runtime["failed_requests"],
        "average_response_time": runtime["average_response_time_ms"],
        "runtime_requests": runtime["total_requests"],
        "rag_usage": runtime["rag_usage_rate"],
        "documents_uploaded": total_documents,
        "recent_sessions": [
            {
                "id": item["id"],
                "chatbot_id": item["resource_id"],
                "chatbot_name": item["resource_name"],
                "project_id": None,
                "project_name": None,
                "version_id": None,
                "user_id": item["actor_id"],
                "channel": "conversation",
                "current_node_key": None,
                "message_count": 0,
                "last_message": "",
                "created_at": item["created_at"],
                "updated_at": item["created_at"],
            }
            for item in recent["items"]
        ],
    }


@router.get("/overview", response_model=AdminDashboardOverview)
def analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return dashboard_overview_payload(db)


@router.get("/platform", response_model=AdminAnalyticsResponse)
def analytics_platform(
    range: str = Query(default="30d", pattern="^(7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return platform_analytics_payload(db, range)


@router.get("/usage", response_model=AdminUsageResponse)
def analytics_usage(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return dashboard_usage(db, days)


@router.get("/channels", response_model=AdminChannelsResponse)
def analytics_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return dashboard_channels(db)


@router.get("/top-chatbots", response_model=list[AdminTopChatbot])
def analytics_top_chatbots(
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return top_chatbots_rows(db, limit)


@router.get("/chatbots", response_model=AdminChatbotsResponse)
def analytics_chatbots(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    publication_status: str | None = Query(default=None),
    deployment_status: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return admin_chatbot_list_payload(
        db,
        page=page,
        page_size=page_size,
        search=search,
        owner_id=owner_id,
        project_id=project_id,
        publication_status=publication_status,
        deployment_status=deployment_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/chatbots/{chatbot_id}", response_model=AdminChatbotDetailsResponse)
def analytics_chatbot_details(
    chatbot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    row = admin_chatbot_base_query(db).filter(Chatbot.id == chatbot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Chatbot not found")

    channels = enabled_channels_for_chatbots(db, [row.chatbot_id])
    return serialize_admin_chatbot_row(row, channels.get(row.chatbot_id, []), include_details=True)


@router.get("/recent-activity", response_model=AdminRecentActivityResponse)
def analytics_recent_activity(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return recent_activity(db, limit)


@router.get("/audit-logs", response_model=AdminAuditLogsResponse)
def analytics_audit_logs(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    actor_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    query = db.query(AuditLog)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            AuditLog.actor_name.ilike(term),
            AuditLog.actor_email.ilike(term),
            AuditLog.resource_name.ilike(term),
            AuditLog.action.ilike(term),
            AuditLog.resource_type.ilike(term),
        ))
    if actor_id:
        query = query.filter(AuditLog.actor_user_id == actor_id)
    if action:
        query = query.filter(AuditLog.action == action.strip().upper())
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type.strip().lower())
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at <= date_to)

    try:
        total = query.count()
        rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    except SQLAlchemyError:
        db.rollback()
        total = 0
        rows = []
    return {
        "items": [
            {
                "id": row.id,
                "created_at": row.created_at,
                "actor_id": row.actor_user_id,
                "actor_name": row.actor_name,
                "actor_email": row.actor_email,
                "actor_role": row.actor_role,
                "action": format_audit_action(row.action),
                "raw_action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "resource_name": row.resource_name,
                "status": row.status,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/system-health", response_model=AdminSystemHealthResponse)
def analytics_system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return system_health(db)


@router.get("/runtime-logs", response_model=AdminRuntimeLogsResponse)
def analytics_runtime_logs(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    chatbot_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    channel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    rag_used: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    Owner = aliased(User)
    query = db.query(
        RuntimeLog.id,
        RuntimeLog.created_at,
        RuntimeLog.chatbot_id,
        Chatbot.name.label("chatbot_name"),
        RuntimeLog.project_id,
        Project.name.label("project_name"),
        Owner.id.label("owner_id"),
        Owner.name.label("owner_name"),
        RuntimeLog.version_id,
        VersionChatbot.version_number,
        RuntimeLog.conversation_id,
        RuntimeLog.channel,
        RuntimeLog.status,
        RuntimeLog.rag_used,
        RuntimeLog.response_time_ms,
        RuntimeLog.error_type,
        RuntimeLog.error_message,
    ).outerjoin(
        Chatbot,
        Chatbot.id == RuntimeLog.chatbot_id,
    ).outerjoin(
        Project,
        Project.id == RuntimeLog.project_id,
    ).outerjoin(
        Owner,
        Owner.id == Project.user_id,
    ).outerjoin(
        VersionChatbot,
        VersionChatbot.id == RuntimeLog.version_id,
    )

    if date_from:
        query = query.filter(RuntimeLog.created_at >= date_from)
    if date_to:
        query = query.filter(RuntimeLog.created_at <= date_to)
    if chatbot_id:
        query = query.filter(RuntimeLog.chatbot_id == chatbot_id)
    if project_id:
        query = query.filter(RuntimeLog.project_id == project_id)
    if owner_id:
        query = query.filter(Owner.id == owner_id)
    if channel:
        query = query.filter(RuntimeLog.channel.in_(runtime_channel_filter_values(channel)))
    if status:
        query = query.filter(RuntimeLog.status == status)
    if rag_used is not None:
        query = query.filter(RuntimeLog.rag_used.is_(rag_used))

    total = query.count()
    rows = query.order_by(RuntimeLog.created_at.desc(), RuntimeLog.id.desc()).offset(offset).limit(limit).all()

    return {
        "items": [
            {
                "id": row.id,
                "created_at": row.created_at,
                "chatbot_id": row.chatbot_id,
                "chatbot_name": row.chatbot_name,
                "project_id": row.project_id,
                "project_name": row.project_name,
                "owner_id": row.owner_id,
                "owner_name": row.owner_name,
                "version_id": row.version_id,
                "version_label": f"v{row.version_number}" if row.version_number is not None else None,
                "conversation_id": row.conversation_id,
                "channel": runtime_channel(row.channel),
                "status": row.status,
                "rag_used": row.rag_used,
                "response_time_ms": row.response_time_ms,
                "error_type": row.error_type,
                "error_message": row.error_message,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/sessions")
def list_sessions(
    chatbot_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    query = db.query(ConversationSession)
    if chatbot_id:
        query = query.filter(ConversationSession.chatbot_id == chatbot_id)

    sessions = query.order_by(ConversationSession.updated_at.desc()).limit(100).all()
    return [serialize_session(db, session) for session in sessions]


@router.get("/sessions/{session_id}")
def session_details(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    session = db.query(ConversationSession).filter(ConversationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    messages = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).order_by(ConversationMessage.created_at.asc()).all()

    return {
        **serialize_session(db, session),
        "variables": session.variables or {},
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "options": message.options or [],
                "sources": message.sources or [],
                "created_at": message.created_at
            }
            for message in messages
        ]
    }
