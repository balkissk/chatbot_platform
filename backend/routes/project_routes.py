from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, union_all
from sqlalchemy.orm import Session
from database.db import SessionLocal
from models.chatbot import Chatbot
from models.chunk import Chunk
from models.conversation import ConversationMessage, ConversationSession
from models.document import Document
from models.flow import Flow, FlowNode, FlowTransition
from models.knowledge_base import KnowledgeBase
from models.llm_config import LLMConfig
from models.project import Project, ProjectStatus
from models.project_schema import (
    ProjectCreate,
    ProjectAnalyticsResponse,
    ProjectListResponse,
    ProjectOverview,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdate,
    ProjectWorkspaceDashboardResponse,
)
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.audit import record_audit_log
from services.flow_validation import validate_flow_version

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def project_query_for_user(db: Session, current_user: User):
    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if current_user.role == "manager":
        query = query.filter(Project.user_id == current_user.id)
    return query


def get_accessible_project(db: Session, project_id: int, current_user: User) -> Project:
    project = project_query_for_user(db, current_user).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def valid_project_statuses() -> set[str]:
    return {status.value for status in ProjectStatus}


def ensure_project_status(value: str) -> str:
    status = value.strip().lower()
    if status not in valid_project_statuses():
        raise HTTPException(status_code=400, detail="Invalid project status")
    return status


def project_activity_subquery():
    runtime_activity = select(
        RuntimeLog.project_id.label("project_id"),
        RuntimeLog.created_at.label("activity_at"),
    ).where(RuntimeLog.project_id.isnot(None))
    conversation_activity = (
        select(Chatbot.project_id.label("project_id"), ConversationSession.updated_at.label("activity_at"))
        .select_from(ConversationSession)
        .join(Chatbot, ConversationSession.chatbot_id == Chatbot.id)
        .where(Chatbot.project_id.isnot(None))
    )
    chatbot_activity = select(
        Chatbot.project_id.label("project_id"),
        Chatbot.created_at.label("activity_at"),
    ).where(Chatbot.project_id.isnot(None))
    activity_union = union_all(runtime_activity, conversation_activity, chatbot_activity).subquery()
    return select(
        activity_union.c.project_id,
        func.max(activity_union.c.activity_at).label("last_activity_at"),
    ).group_by(activity_union.c.project_id).subquery()


def project_stats_for_ids(db: Session, project_ids: list[int]) -> dict[int, dict]:
    stats = {
        project_id: {
            "chatbot_count": 0,
            "version_count": 0,
            "published_version_count": 0,
            "draft_version_count": 0,
            "archived_version_count": 0,
            "assistant_count": 0,
            "active_assistant_count": 0,
            "published_assistant_count": 0,
            "draft_only_assistant_count": 0,
            "last_activity_at": None,
        }
        for project_id in project_ids
    }
    if not project_ids:
        return stats

    chatbot_rows = db.query(
        Chatbot.project_id,
        func.count(Chatbot.id)
    ).filter(
        Chatbot.project_id.in_(project_ids)
    ).group_by(Chatbot.project_id).all()

    for project_id, count in chatbot_rows:
        stats[project_id]["chatbot_count"] = count
        stats[project_id]["assistant_count"] = count

    active_chatbot_rows = db.query(
        Chatbot.project_id,
        func.count(Chatbot.id)
    ).filter(
        Chatbot.project_id.in_(project_ids),
        Chatbot.is_active.is_(True),
    ).group_by(Chatbot.project_id).all()

    for project_id, count in active_chatbot_rows:
        stats[project_id]["active_assistant_count"] = count

    version_rows = db.query(
        Chatbot.project_id,
        VersionChatbot.status,
        func.count(VersionChatbot.id)
    ).join(
        Chatbot,
        VersionChatbot.chatbot_id == Chatbot.id
    ).filter(
        Chatbot.project_id.in_(project_ids)
    ).group_by(Chatbot.project_id, VersionChatbot.status).all()

    for project_id, status, count in version_rows:
        stats[project_id]["version_count"] += count
        if status == "published":
            stats[project_id]["published_version_count"] = count
        elif status == "draft":
            stats[project_id]["draft_version_count"] = count
        elif status == "archived":
            stats[project_id]["archived_version_count"] = count

    published_assistant_rows = db.query(
        Chatbot.project_id,
        func.count(Chatbot.id),
    ).join(
        VersionChatbot,
        VersionChatbot.id == Chatbot.active_version_id,
    ).filter(
        Chatbot.project_id.in_(project_ids),
        Chatbot.is_active.is_(True),
        VersionChatbot.status == "published",
    ).group_by(Chatbot.project_id).all()

    for project_id, count in published_assistant_rows:
        stats[project_id]["published_assistant_count"] = count

    for project_id, values in stats.items():
        values["draft_only_assistant_count"] = max(
            values["active_assistant_count"] - values["published_assistant_count"],
            0,
        )

    runtime_rows = db.query(
        RuntimeLog.project_id,
        func.max(RuntimeLog.created_at),
    ).filter(
        RuntimeLog.project_id.in_(project_ids)
    ).group_by(RuntimeLog.project_id).all()

    for project_id, last_activity in runtime_rows:
        stats[project_id]["last_activity_at"] = last_activity

    conversation_rows = db.query(
        Chatbot.project_id,
        func.max(ConversationSession.updated_at),
    ).join(
        ConversationSession,
        ConversationSession.chatbot_id == Chatbot.id,
    ).filter(
        Chatbot.project_id.in_(project_ids)
    ).group_by(Chatbot.project_id).all()

    for project_id, last_activity in conversation_rows:
        existing = stats[project_id]["last_activity_at"]
        if existing is None or (last_activity is not None and last_activity > existing):
            stats[project_id]["last_activity_at"] = last_activity

    chatbot_activity_rows = db.query(
        Chatbot.project_id,
        func.max(Chatbot.created_at),
    ).filter(
        Chatbot.project_id.in_(project_ids)
    ).group_by(Chatbot.project_id).all()

    for project_id, last_activity in chatbot_activity_rows:
        existing = stats[project_id]["last_activity_at"]
        if existing is None or (last_activity is not None and last_activity > existing):
            stats[project_id]["last_activity_at"] = last_activity

    return stats


def serialize_project(project: Project, stats: dict | None = None) -> dict:
    stats_payload = stats or {
        "chatbot_count": 0,
        "version_count": 0,
        "published_version_count": 0,
        "draft_version_count": 0,
        "archived_version_count": 0,
        "assistant_count": 0,
        "active_assistant_count": 0,
        "published_assistant_count": 0,
        "draft_only_assistant_count": 0,
        "last_activity_at": None,
    }
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "user_id": project.user_id,
        "status": project.status or ProjectStatus.active.value,
        "created_at": project.created_at,
        "archived_at": project.archived_at,
        "deleted_at": project.deleted_at,
        "assistants_count": stats_payload["assistant_count"],
        "published_assistants_count": stats_payload["published_assistant_count"],
        "draft_assistants_count": stats_payload["draft_only_assistant_count"],
        "last_activity": stats_payload["last_activity_at"],
        "health_status": project_health_status(project, stats_payload),
        **stats_payload,
    }


def project_health_status(project: Project, stats: dict) -> str | None:
    lifecycle = (project.status or ProjectStatus.active.value).lower()
    if lifecycle in {ProjectStatus.archived.value, ProjectStatus.disabled.value}:
        return None
    if stats.get("active_assistant_count", 0) == 0:
        return "Needs setup"
    if stats.get("published_assistant_count", 0) > 0:
        return "Live"
    return "Ready to deploy"


def normalize_project_list_status(status: str | None) -> list[str]:
    if not status or status.strip().lower() == "all":
        return [ProjectStatus.active.value, ProjectStatus.draft.value]
    normalized = ensure_project_status(status)
    return [normalized]


def apply_project_list_filters(
    query,
    *,
    db: Session,
    current_user: User,
    search: str | None,
    status: str | None,
    owner_id: int | None,
    created_from: date | None,
    created_to: date | None,
    last_activity_from: date | None = None,
    last_activity_to: date | None = None,
    assistant_range: str | None = None,
):
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.name.ilike(term), Project.description.ilike(term)))

    statuses = normalize_project_list_status(status)
    query = query.filter(Project.status.in_(statuses))

    if owner_id is not None:
        if current_user.role == "manager" and owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Managers can only filter their own projects")
        query = query.filter(Project.user_id == owner_id)

    if created_from:
        query = query.filter(Project.created_at >= datetime.combine(created_from, datetime.min.time()))

    if created_to:
        query = query.filter(Project.created_at <= datetime.combine(created_to, datetime.max.time()))

    activity = project_activity_subquery()
    if last_activity_from or last_activity_to:
        query = query.outerjoin(activity, activity.c.project_id == Project.id)
        activity_value = func.coalesce(activity.c.last_activity_at, Project.created_at)
        if last_activity_from:
            query = query.filter(activity_value >= datetime.combine(last_activity_from, datetime.min.time()))
        if last_activity_to:
            query = query.filter(activity_value <= datetime.combine(last_activity_to, datetime.max.time()))

    if assistant_range and assistant_range != "any":
        assistant_counts = db.query(
            Chatbot.project_id.label("project_id"),
            func.count(Chatbot.id).label("assistant_count"),
        ).group_by(Chatbot.project_id).subquery()
        query = query.outerjoin(assistant_counts, assistant_counts.c.project_id == Project.id)
        count_value = func.coalesce(assistant_counts.c.assistant_count, 0)
        if assistant_range == "none":
            query = query.filter(count_value == 0)
        elif assistant_range == "1-5":
            query = query.filter(count_value.between(1, 5))
        elif assistant_range == "6-10":
            query = query.filter(count_value.between(6, 10))
        elif assistant_range == "10+":
            query = query.filter(count_value > 10)

    return query


def apply_project_sort(query, sort: str, db: Session):
    if sort == "assistants":
        assistant_counts = db.query(
            Chatbot.project_id.label("project_id"),
            func.count(Chatbot.id).label("assistant_count"),
        ).group_by(Chatbot.project_id).subquery()
        return query.outerjoin(assistant_counts, assistant_counts.c.project_id == Project.id).order_by(
            func.coalesce(assistant_counts.c.assistant_count, 0).desc(),
            Project.created_at.desc(),
        )
    if sort == "name":
        return query.order_by(func.lower(Project.name).asc(), Project.created_at.desc())
    if sort in {"created", "created_at", "created_date"}:
        return query.order_by(Project.created_at.desc())
    if sort in {"recent", "recent_activity", "activity"}:
        activity = project_activity_subquery()
        return query.outerjoin(activity, activity.c.project_id == Project.id).order_by(
            func.coalesce(activity.c.last_activity_at, Project.created_at).desc(),
            Project.created_at.desc(),
        )
    raise HTTPException(status_code=400, detail="Invalid project sort")


def project_summary_for_user(db: Session, current_user: User) -> ProjectSummaryResponse:
    project_ids = [project_id for (project_id,) in project_query_for_user(db, current_user).with_entities(Project.id).all()]
    stats = project_stats_for_ids(db, project_ids)
    return ProjectSummaryResponse(
        projects=len(project_ids),
        assistants=sum(item["assistant_count"] for item in stats.values()),
        published_assistants=sum(item["published_assistant_count"] for item in stats.values()),
        draft_only=sum(item["draft_only_assistant_count"] for item in stats.values()),
    )


def percent_or_none(part: int, total: int) -> int | None:
    return round((part / total) * 100) if total else None


def safe_preview(value: str | None, max_length: int = 180) -> str:
    text_value = (value or "").strip()
    return text_value[:max_length]


SMALL_TALK_QUESTIONS = {
    "hi",
    "hello",
    "hey",
    "bonjour",
    "bonsoir",
    "salut",
    "merci",
    "thanks",
    "thank you",
    "ok",
    "okay",
    "cava",
    "ça va",
    "ca va",
}


def is_substantive_knowledge_question(value: str | None) -> bool:
    normalized = " ".join((value or "").strip().lower().split())
    if not normalized:
        return False
    if normalized in SMALL_TALK_QUESTIONS:
        return False
    tokens = normalized.split()
    return len(tokens) >= 3 or "?" in normalized


def is_searchable_chunk(chunk: Chunk) -> bool:
    return chunk.embedding_status == "ready" and bool(
        getattr(chunk, "embedding_vector", None) or chunk.embedding
    )


def is_no_published_version_error(log: RuntimeLog) -> bool:
    message = f"{log.error_type or ''} {log.error_message or ''}".lower()
    return "no published version" in message or "has no published version" in message


def message_response_mode(message: ConversationMessage) -> str:
    if message.role != "bot":
        return ""
    if message.sources:
        return "ai_rag"

    content = (message.content or "").lower()
    fallback_markers = [
        "not contain enough information",
        "no relevant context",
        "not confirmed by the uploaded documents",
        "does not contain enough information",
        "i don't know",
        "je ne sais pas",
        "pas assez d'informations",
    ]
    if any(marker in content for marker in fallback_markers):
        return "fallback"
    return "flow"


def latency_ms(user_message: ConversationMessage | None, bot_message: ConversationMessage | None) -> int | None:
    if not user_message or not bot_message or not user_message.created_at or not bot_message.created_at:
        return None
    return max(0, round((bot_message.created_at - user_message.created_at).total_seconds() * 1000))


def grouped_messages_for_sessions(db: Session, session_ids: list[int]) -> dict[int, list[ConversationMessage]]:
    if not session_ids:
        return {}
    rows = db.query(ConversationMessage).filter(
        ConversationMessage.session_id.in_(session_ids)
    ).order_by(ConversationMessage.session_id.asc(), ConversationMessage.created_at.asc()).all()

    grouped: dict[int, list[ConversationMessage]] = {}
    for message in rows:
        grouped.setdefault(message.session_id, []).append(message)
    return grouped


def version_payload(version: VersionChatbot | None) -> dict | None:
    if not version:
        return None
    return {
        "id": version.id,
        "version_number": version.version_number,
        "status": version.status,
        "created_at": version.created_at,
        "published_at": version.published_at,
    }


def duplicate_project_name(db: Session, source: Project, current_user: User) -> str:
    base_name = f"{source.name} Copy"
    query = project_query_for_user(db, current_user)
    existing_names = {
        name for (name,) in query.filter(Project.name.ilike(f"{base_name}%")).with_entities(Project.name).all()
    }
    if base_name not in existing_names:
        return base_name
    suffix = 2
    while f"{base_name} {suffix}" in existing_names:
        suffix += 1
    return f"{base_name} {suffix}"

@router.post("/projects", response_model=ProjectResponse)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    name = project.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    new_project = Project(
        name=name,
        description=project.description.strip() or "No description",
        user_id=current_user.id,
        status=ProjectStatus.active.value,
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_CREATED",
        resource_type="project",
        resource_id=new_project.id,
        resource_name=new_project.name,
    )

    stats = project_stats_for_ids(db, [new_project.id])
    return serialize_project(new_project, stats.get(new_project.id))

@router.get("/projects", response_model=list[ProjectResponse])
def get_projects(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
    status: str | None = None,
    owner_id: int | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    sort: str = "recent_activity",
    page: int | None = None,
    page_size: int | None = None,
):
    if not isinstance(search, str):
        search = None
    if not isinstance(limit, int):
        limit = 50
    if not isinstance(offset, int):
        offset = 0
    if page is not None and page < 1:
        raise HTTPException(status_code=400, detail="Page must be greater than zero")
    if page_size is not None and (page_size < 1 or page_size > 100):
        raise HTTPException(status_code=400, detail="Page size must be between 1 and 100")

    query = project_query_for_user(db, current_user)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.name.ilike(term), Project.description.ilike(term)))

    if status:
        query = query.filter(Project.status == ensure_project_status(status))

    if owner_id is not None:
        if current_user.role == "manager" and owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Managers can only filter their own projects")
        query = query.filter(Project.user_id == owner_id)

    if created_from:
        query = query.filter(Project.created_at >= datetime.combine(created_from, datetime.min.time()))

    if created_to:
        query = query.filter(Project.created_at <= datetime.combine(created_to, datetime.max.time()))

    assistant_counts = db.query(
        Chatbot.project_id.label("project_id"),
        func.count(Chatbot.id).label("assistant_count"),
    ).group_by(Chatbot.project_id).subquery()

    if sort == "assistants":
        query = query.outerjoin(assistant_counts, assistant_counts.c.project_id == Project.id).order_by(
            func.coalesce(assistant_counts.c.assistant_count, 0).desc(),
            Project.created_at.desc(),
        )
    elif sort == "name":
        query = query.order_by(func.lower(Project.name).asc(), Project.created_at.desc())
    elif sort in {"created", "created_at", "created_date"}:
        query = query.order_by(Project.created_at.desc())
    elif sort in {"recent", "recent_activity", "activity"}:
        activity = project_activity_subquery()
        query = query.outerjoin(activity, activity.c.project_id == Project.id).order_by(
            func.coalesce(activity.c.last_activity_at, Project.created_at).desc(),
            Project.created_at.desc(),
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid project sort")

    if page is not None or page_size is not None:
        effective_page_size = page_size or limit
        effective_page = page or 1
        offset = (effective_page - 1) * effective_page_size
        limit = effective_page_size

    projects = query.offset(offset).limit(limit).all()
    stats = project_stats_for_ids(db, [project.id for project in projects])
    return [serialize_project(project, stats.get(project.id)) for project in projects]


@router.get("/projects/summary", response_model=ProjectSummaryResponse)
def get_projects_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    return project_summary_for_user(db, current_user)


@router.get("/projects/query", response_model=ProjectListResponse)
def query_projects(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    owner_id: int | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    last_activity_from: date | None = None,
    last_activity_to: date | None = None,
    assistant_range: str | None = Query(default=None),
    sort: str = "recent_activity",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    if not isinstance(search, str):
        search = None
    if not isinstance(status, str):
        status = None
    if not isinstance(assistant_range, str):
        assistant_range = None
    query = project_query_for_user(db, current_user)
    query = apply_project_list_filters(
        query,
        db=db,
        current_user=current_user,
        search=search,
        status=status,
        owner_id=owner_id,
        created_from=created_from,
        created_to=created_to,
        last_activity_from=last_activity_from,
        last_activity_to=last_activity_to,
        assistant_range=assistant_range,
    )
    total = query.count()
    query = apply_project_sort(query, sort, db)
    projects = query.offset((page - 1) * page_size).limit(page_size).all()
    stats = project_stats_for_ids(db, [project.id for project in projects])
    return ProjectListResponse(
        items=[serialize_project(project, stats.get(project.id)) for project in projects],
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
        has_previous=page > 1,
    )


@router.get("/projects/{project_id}", response_model=ProjectOverview)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    stats = project_stats_for_ids(db, [project.id])
    return serialize_project(project, stats.get(project.id))


@router.get("/projects/{project_id}/analytics", response_model=ProjectAnalyticsResponse)
def get_project_analytics(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    stats = project_stats_for_ids(db, [project.id]).get(project.id)
    chatbots = db.query(Chatbot).filter(Chatbot.project_id == project.id).all()
    chatbot_ids = [chatbot.id for chatbot in chatbots]

    sessions_query = db.query(ConversationSession).join(Chatbot, ConversationSession.chatbot_id == Chatbot.id).filter(
        Chatbot.project_id == project.id
    )
    conversations_count = sessions_query.count()
    session_ids = [row.id for row in sessions_query.with_entities(ConversationSession.id).all()]

    messages_count = db.query(ConversationMessage.id).filter(
        ConversationMessage.session_id.in_(session_ids)
    ).count() if session_ids else 0

    runtime_query = db.query(RuntimeLog).filter(
        or_(RuntimeLog.project_id == project.id, RuntimeLog.chatbot_id.in_(chatbot_ids))
    ) if chatbot_ids else db.query(RuntimeLog).filter(RuntimeLog.project_id == project.id)
    runtime_request_count = runtime_query.count()
    runtime_failure_count = runtime_query.filter(RuntimeLog.status == "failed").count()
    runtime_success_count = runtime_query.filter(RuntimeLog.status == "success").count()
    runtime_success_rate = percent_or_none(runtime_success_count, runtime_request_count)
    average_response_latency = runtime_query.filter(RuntimeLog.response_time_ms.isnot(None)).with_entities(
        func.avg(RuntimeLog.response_time_ms)
    ).scalar()

    bot_messages = db.query(ConversationMessage).filter(
        ConversationMessage.session_id.in_(session_ids),
        ConversationMessage.role == "bot",
    ).all() if session_ids else []
    fallback_count = sum(1 for message in bot_messages if message_response_mode(message) == "fallback")
    fallback_rate = percent_or_none(fallback_count, len(bot_messages))

    usage_by_channel = [
        {"channel": channel or "unknown", "count": count}
        for channel, count in runtime_query.with_entities(
            RuntimeLog.channel,
            func.count(RuntimeLog.id),
        ).group_by(RuntimeLog.channel).order_by(func.count(RuntimeLog.id).desc()).all()
    ]

    recent_errors = [
        {
            "id": log.id,
            "channel": log.channel,
            "status": log.status,
            "message": safe_preview(log.error_message or log.error_type or "Runtime execution failed."),
            "created_at": log.created_at,
            "response_time_ms": log.response_time_ms,
        }
        for log in runtime_query.filter(RuntimeLog.status == "failed").order_by(RuntimeLog.created_at.desc()).limit(10).all()
    ]

    return {
        "project": serialize_project(project, stats),
        "kpis": {
            "conversations_count": conversations_count,
            "messages_count": messages_count,
            "runtime_request_count": runtime_request_count,
            "runtime_success_rate": runtime_success_rate,
            "runtime_failure_count": runtime_failure_count,
            "average_response_latency_ms": round(average_response_latency) if average_response_latency is not None else None,
            "fallback_count": fallback_count,
            "fallback_rate": fallback_rate,
            "active_assistants_count": stats.get("active_assistant_count", 0) if stats else 0,
            "published_assistants_count": stats.get("published_assistant_count", 0) if stats else 0,
            "draft_assistants_count": stats.get("draft_only_assistant_count", 0) if stats else 0,
        },
        "usage_by_channel": usage_by_channel,
        "recent_errors": recent_errors,
    }


@router.get("/projects/{project_id}/workspace-dashboard", response_model=ProjectWorkspaceDashboardResponse)
def get_project_workspace_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    stats = project_stats_for_ids(db, [project.id]).get(project.id)
    chatbots = db.query(Chatbot).filter(Chatbot.project_id == project.id).all()
    chatbot_ids = [chatbot.id for chatbot in chatbots]
    chatbot_by_id = {chatbot.id: chatbot for chatbot in chatbots}

    versions = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id.in_(chatbot_ids)
    ).order_by(VersionChatbot.version_number.desc()).all() if chatbot_ids else []
    versions_by_chatbot: dict[int, list[VersionChatbot]] = {}
    for version in versions:
        versions_by_chatbot.setdefault(version.chatbot_id, []).append(version)

    latest_versions = [
        rows[0] for rows in versions_by_chatbot.values()
        if rows
    ]
    latest_version = max(latest_versions, key=lambda row: row.created_at or datetime.min) if latest_versions else None
    published_versions = [version for version in versions if version.status == "published"]
    published_version = max(
        published_versions,
        key=lambda row: row.published_at or row.created_at or datetime.min,
    ) if published_versions else None

    version_ids = [version.id for version in versions]
    knowledge_base_ids = [
        row.id for row in db.query(KnowledgeBase.id).filter(KnowledgeBase.version_id.in_(version_ids)).all()
    ] if version_ids else []
    documents = db.query(Document).filter(Document.knowledge_base_id.in_(knowledge_base_ids)).all() if knowledge_base_ids else []
    document_ids = [document.id for document in documents]
    chunks = db.query(Chunk).filter(Chunk.document_id.in_(document_ids)).all() if document_ids else []
    failed_documents = [document for document in documents if document.status == "failed" or document.error_message]
    processing_documents = [document for document in documents if document.status in {"processing", "uploaded"}]
    failed_embeddings = [chunk for chunk in chunks if chunk.embedding_status == "failed" or chunk.embedding_error]
    ready_embeddings = [chunk for chunk in chunks if is_searchable_chunk(chunk)]

    ready_kb_version_ids = {
        version_id for (version_id,) in db.query(KnowledgeBase.version_id)
        .join(Document, Document.knowledge_base_id == KnowledgeBase.id)
        .join(Chunk, Chunk.document_id == Document.id)
        .filter(
            KnowledgeBase.version_id.in_(version_ids),
            Chunk.embedding_status == "ready",
            or_(Chunk.embedding_vector.isnot(None), Chunk.embedding.isnot(None)),
        )
        .distinct()
        .all()
    } if version_ids else set()

    sessions = db.query(ConversationSession).filter(
        ConversationSession.chatbot_id.in_(chatbot_ids)
    ).order_by(ConversationSession.updated_at.desc()).limit(300).all() if chatbot_ids else []
    grouped_messages = grouped_messages_for_sessions(db, [session.id for session in sessions])

    eligible_questions = 0
    retrieved_questions = 0
    fallback_signals = []
    quality_signals = []
    for session in sessions:
        messages = grouped_messages.get(session.id, [])
        is_rag_capable_session = session.version_id in ready_kb_version_ids
        previous_user: ConversationMessage | None = None
        for message in messages:
            if message.role == "user":
                previous_user = message
                if is_rag_capable_session and is_substantive_knowledge_question(message.content):
                    eligible_questions += 1
                continue
            if message.role != "bot" or not previous_user:
                continue
            mode = message_response_mode(message)
            substantive_question = is_substantive_knowledge_question(previous_user.content)
            if is_rag_capable_session and substantive_question and message.sources:
                retrieved_questions += 1
            if mode == "fallback":
                if substantive_question:
                    fallback_signals.append({
                        "question": previous_user.content,
                        "count": 1,
                        "last_asked_at": previous_user.created_at,
                        "session_id": session.id,
                    })
                    quality_signals.append({
                        "session_id": session.id,
                        "user_message": safe_preview(previous_user.content, 120),
                        "ai_response": safe_preview(message.content, 120),
                        "retrieved_chunks": message.sources or [],
                        "latency_ms": latency_ms(previous_user, message),
                        "issue_type": "Fallback response",
                        "severity": "warning",
                        "reason": "The assistant could not answer a substantive user question from available knowledge.",
                        "created_at": message.created_at,
                        "updated_at": session.updated_at,
                    })
            elif is_rag_capable_session and substantive_question and not message.sources:
                quality_signals.append({
                    "session_id": session.id,
                    "user_message": safe_preview(previous_user.content, 120),
                    "ai_response": safe_preview(message.content, 120),
                    "retrieved_chunks": [],
                    "latency_ms": latency_ms(previous_user, message),
                    "issue_type": "Zero retrieved chunks",
                    "severity": "warning",
                    "reason": "A substantive question received no retrieved knowledge chunks.",
                    "created_at": message.created_at,
                    "updated_at": session.updated_at,
                })
            previous_user = None

    gap_rows: dict[str, dict] = {}
    for row in fallback_signals:
        question = (row["question"] or "").strip()
        if not question:
            continue
        key = " ".join(question.lower().split())
        existing = gap_rows.setdefault(key, {
            "question": question,
            "count": 0,
            "last_asked_at": row["last_asked_at"],
            "session_id": row["session_id"],
        })
        existing["count"] += 1
        if row["last_asked_at"] and (not existing["last_asked_at"] or row["last_asked_at"] > existing["last_asked_at"]):
            existing["last_asked_at"] = row["last_asked_at"]
            existing["session_id"] = row["session_id"]
    knowledge_gaps = sorted(
        [row for row in gap_rows.values() if row["count"] > 1],
        key=lambda item: (item["count"], item["last_asked_at"] or datetime.min),
        reverse=True,
    )[:8]

    runtime_query = db.query(RuntimeLog).filter(
        or_(RuntimeLog.project_id == project.id, RuntimeLog.chatbot_id.in_(chatbot_ids))
    ) if chatbot_ids else db.query(RuntimeLog).filter(RuntimeLog.project_id == project.id)
    runtime_total = runtime_query.count()
    runtime_success = runtime_query.filter(RuntimeLog.status == "success").count()
    runtime_failed = runtime_query.filter(RuntimeLog.status == "failed").count()
    runtime_success_rate = percent_or_none(runtime_success, runtime_total)
    average_response_time = runtime_query.filter(RuntimeLog.response_time_ms.isnot(None)).with_entities(
        func.avg(RuntimeLog.response_time_ms)
    ).scalar()

    runtime_alerts = runtime_query.filter(RuntimeLog.status == "failed").order_by(
        RuntimeLog.created_at.desc()
    ).limit(5).all()
    slow_runtime_logs = runtime_query.filter(
        RuntimeLog.response_time_ms.isnot(None),
        RuntimeLog.response_time_ms >= 5000,
    ).order_by(RuntimeLog.created_at.desc()).limit(3).all()

    operational_alerts = []
    for log in runtime_alerts:
        affected = chatbot_by_id.get(log.chatbot_id)
        publication_issue = is_no_published_version_error(log)
        operational_alerts.append({
            "type": "warning" if publication_issue else "error",
            "severity": "warning" if publication_issue else "critical",
            "category": "publication" if publication_issue else "runtime",
            "title": "Publication blocker" if publication_issue else "Runtime failure",
            "message": safe_preview(log.error_message or log.error_type or "Runtime execution failed."),
            "created_at": log.created_at,
            "source": "versions" if publication_issue else "runtime",
            "affected_assistant_id": affected.id if affected else None,
            "affected_assistant_name": affected.name if affected else None,
        })
    for document in sorted(failed_documents + processing_documents, key=lambda item: item.created_at or datetime.min, reverse=True)[:5]:
        is_failed = document.status == "failed" or document.error_message
        operational_alerts.append({
            "type": "error" if is_failed else "warning",
            "severity": "critical" if is_failed else "warning",
            "category": "knowledge_base",
            "title": "Document processing failed" if is_failed else "Document processing pending",
            "message": safe_preview(document.error_message or document.filename),
            "created_at": document.created_at,
            "source": "knowledge_base",
        })
    operational_alerts = sorted(
        operational_alerts,
        key=lambda item: item.get("created_at") or datetime.min,
        reverse=True,
    )[:8]

    for log in runtime_alerts:
        affected = chatbot_by_id.get(log.chatbot_id)
        publication_issue = is_no_published_version_error(log)
        quality_signals.append({
            "session_id": log.conversation_id,
            "user_message": "",
            "ai_response": safe_preview(log.error_message or log.error_type or "Runtime execution failed."),
            "retrieved_chunks": [],
            "latency_ms": log.response_time_ms,
            "issue_type": "Publication blocker" if publication_issue else "Runtime error",
            "severity": "warning" if publication_issue else "critical",
            "reason": (
                f"{affected.name} has no published version available for runtime."
                if publication_issue and affected
                else "A persisted runtime execution failed."
            ),
            "created_at": log.created_at,
            "updated_at": log.completed_at or log.created_at,
        })
    for log in slow_runtime_logs:
        quality_signals.append({
            "session_id": log.conversation_id,
            "user_message": "",
            "ai_response": "",
            "retrieved_chunks": [],
            "latency_ms": log.response_time_ms,
            "issue_type": "Slow response",
            "severity": "warning",
            "reason": "The response exceeded the current 5 second dashboard threshold.",
            "created_at": log.created_at,
            "updated_at": log.completed_at or log.created_at,
        })
    quality_signals = sorted(
        quality_signals,
        key=lambda item: item.get("updated_at") or item.get("created_at") or datetime.min,
        reverse=True,
    )[:5]

    flow_results = []
    flow_valid_by_chatbot: dict[int, bool] = {}
    llm_ready_count = 0
    active_chatbots = [chatbot for chatbot in chatbots if chatbot.is_active]
    for chatbot in active_chatbots:
        latest = versions_by_chatbot.get(chatbot.id, [None])[0]
        if latest:
            is_flow_valid = validate_flow_version(db, latest.id).get("valid", False)
            flow_results.append(is_flow_valid)
            flow_valid_by_chatbot[chatbot.id] = is_flow_valid
            llm_config = db.query(LLMConfig).filter(LLMConfig.version_id == latest.id).first()
            if llm_config and llm_config.model:
                llm_ready_count += 1
        else:
            flow_results.append(False)
            flow_valid_by_chatbot[chatbot.id] = False

    has_active_assistants = bool(active_chatbots)
    flow_ready = has_active_assistants and all(flow_results)
    kb_ready = not failed_documents and not failed_embeddings and (
        not documents or (bool(chunks) and len(ready_embeddings) == len(chunks))
    )
    ai_ready = has_active_assistants and llm_ready_count == len(active_chatbots)
    publication_ready = flow_ready and ai_ready and kb_ready

    readiness_center = [
        {
            "label": "Flow Validation",
            "status": "ready" if flow_ready else "needs_attention",
            "message": "All active assistants have valid latest flows." if flow_ready else "One or more active assistants need flow validation.",
        },
        {
            "label": "Knowledge Base",
            "status": "ready" if kb_ready else "needs_attention",
            "message": "Knowledge Base is optional or all searchable chunks are ready." if kb_ready else "Resolve failed, pending, or legacy Knowledge Base embeddings.",
        },
        {
            "label": "AI Configuration",
            "status": "ready" if ai_ready else "needs_attention",
            "message": "All active assistants have model configuration." if ai_ready else "Configure the model for each active assistant.",
        },
        {
            "label": "Publication Readiness",
            "status": "ready" if publication_ready else "needs_attention",
            "message": "Latest active assistant versions are publishable." if publication_ready else "Fix flow, AI configuration, or Knowledge Base issues before publishing.",
        },
    ]

    recommendations = []
    if failed_documents or failed_embeddings:
        recommendations.append({
            "title": "Resolve Knowledge Base processing issues",
            "message": f"{len(failed_documents)} document and {len(failed_embeddings)} embedding issue(s) need attention.",
            "priority": "high",
            "action": "knowledge",
            "expected_impact": "Restores searchable knowledge for grounded answers.",
        })
    if knowledge_gaps:
        recommendations.append({
            "title": "Add Knowledge Base content",
            "message": f"{len(knowledge_gaps)} recurring knowledge gap(s) were detected from fallback answers.",
            "priority": "high",
            "action": "knowledge",
            "expected_impact": "Improves answers for repeated unanswered questions.",
        })
    if runtime_total and runtime_failed:
        failed_without_publication = [log for log in runtime_alerts if is_no_published_version_error(log)]
        recommendations.append({
            "title": "Publish or fix unavailable assistants" if failed_without_publication else "Investigate runtime failures",
            "message": (
                f"{len(failed_without_publication)} runtime request(s) failed because an assistant has no published version."
                if failed_without_publication
                else f"{runtime_failed} of {runtime_total} persisted runtime execution(s) failed."
            ),
            "priority": "high" if (runtime_failed / runtime_total) >= 0.1 else "medium",
            "action": "versions" if failed_without_publication else "analytics",
            "affected_assistant_id": failed_without_publication[0].chatbot_id if failed_without_publication else None,
            "affected_assistant_name": (
                chatbot_by_id.get(failed_without_publication[0].chatbot_id).name
                if failed_without_publication and chatbot_by_id.get(failed_without_publication[0].chatbot_id)
                else None
            ),
            "expected_impact": "Restores live runtime availability." if failed_without_publication else "Improves reliability and success rate.",
        })
    if not published_version and latest_version:
        recommendations.append({
            "title": "Publish the latest version",
            "message": "No published version is currently available for this workspace.",
            "priority": "medium",
            "action": "versions",
            "expected_impact": "Makes the assistant available to runtime channels.",
        })
    if not flow_ready and active_chatbots:
        affected_flow_bot = next(
            (
                chatbot for chatbot in active_chatbots
                if not flow_valid_by_chatbot.get(chatbot.id, False)
            ),
            None,
        )
        recommendations.append({
            "title": "Resolve flow validation issues",
            "message": "At least one active assistant has a latest flow that is not publication-ready.",
            "priority": "high",
            "action": "flow",
            "affected_assistant_id": affected_flow_bot.id if affected_flow_bot else None,
            "affected_assistant_name": affected_flow_bot.name if affected_flow_bot else None,
            "expected_impact": "Removes publish blockers and prevents broken conversations.",
        })

    metrics = [
        {
            "label": "Knowledge Answer Coverage",
            "value": percent_or_none(retrieved_questions, eligible_questions),
            "suffix": "%",
            "helper": f"{retrieved_questions} of {eligible_questions} eligible RAG questions retrieved chunks" if eligible_questions else "No eligible RAG questions yet",
            "tone": "coverage",
        },
        {
            "label": "Runtime Requests",
            "value": runtime_total,
            "helper": f"{runtime_success} successful, {runtime_failed} failed persisted executions · all time",
            "tone": "resolution",
        },
        {
            "label": "Runtime Success Rate",
            "value": runtime_success_rate,
            "suffix": "%",
            "helper": "No persisted runtime requests yet" if runtime_success_rate is None else f"Average response time {round(average_response_time or 0)} ms · all time",
            "tone": "health",
        },
        {
            "label": "Version State",
            "value": f"v{latest_version.version_number}" if latest_version else None,
            "helper": (
                f"Latest {latest_version.status}; published v{published_version.version_number}"
                if latest_version and published_version
                else ("No published version yet" if latest_version else "No versions yet")
            ),
            "tone": "version",
        },
    ]

    return {
        "project": serialize_project(project, stats),
        "summary": {
            "total_assistants": stats.get("assistant_count", 0) if stats else 0,
            "published_assistants": stats.get("published_assistant_count", 0) if stats else 0,
            "draft_only_assistants": stats.get("draft_only_assistant_count", 0) if stats else 0,
        },
        "metrics": metrics,
        "readiness_center": readiness_center,
        "recommended_actions": recommendations[:6],
        "knowledge_gaps": knowledge_gaps,
        "release_state": {
            "latest_version": version_payload(latest_version),
            "latest_version_status": latest_version.status if latest_version else None,
            "published_version": version_payload(published_version),
            "last_published_at": published_version.published_at if published_version else None,
            "rollback_available": len(published_versions) > 1,
        },
        "operational_alerts": operational_alerts,
        "quality_signals": quality_signals,
    }


@router.put("/projects/{project_id}/archive", response_model=ProjectResponse)
def archive_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    if project.status == ProjectStatus.archived.value:
        stats = project_stats_for_ids(db, [project.id])
        return serialize_project(project, stats.get(project.id))

    project.status = ProjectStatus.archived.value
    project.archived_at = datetime.utcnow()
    db.commit()
    db.refresh(project)

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_ARCHIVED",
        resource_type="project",
        resource_id=project.id,
        resource_name=project.name,
    )

    stats = project_stats_for_ids(db, [project.id])
    return serialize_project(project, stats.get(project.id))


@router.put("/projects/{project_id}/restore", response_model=ProjectResponse)
def restore_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    project.status = ProjectStatus.active.value
    project.archived_at = None
    db.commit()
    db.refresh(project)

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_RESTORED",
        resource_type="project",
        resource_id=project.id,
        resource_name=project.name,
    )

    stats = project_stats_for_ids(db, [project.id])
    return serialize_project(project, stats.get(project.id))


@router.post("/projects/{project_id}/duplicate", response_model=ProjectResponse)
def duplicate_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    source = get_accessible_project(db, project_id, current_user)
    duplicate = Project(
        name=duplicate_project_name(db, source, current_user),
        description=source.description,
        user_id=current_user.id if current_user.role == "manager" else source.user_id,
        status=ProjectStatus.active.value,
    )
    db.add(duplicate)
    db.commit()
    db.refresh(duplicate)

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_DUPLICATED",
        resource_type="project",
        resource_id=duplicate.id,
        resource_name=duplicate.name,
        metadata={"source_project_id": source.id},
    )

    stats = project_stats_for_ids(db, [duplicate.id])
    return serialize_project(duplicate, stats.get(duplicate.id))


@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    name = payload.name.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    previous_name = project.name
    project.name = name
    project.description = payload.description.strip() or "No description"
    db.commit()
    db.refresh(project)

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_RENAMED" if previous_name != project.name else "PROJECT_UPDATED",
        resource_type="project",
        resource_id=project.id,
        resource_name=project.name,
        metadata={"previous_name": previous_name} if previous_name != project.name else None,
    )

    stats = project_stats_for_ids(db, [project.id])
    return serialize_project(project, stats.get(project.id))


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    deleted_project_id = project.id
    deleted_project_name = project.name

    now = datetime.utcnow()
    project.status = ProjectStatus.disabled.value
    project.deleted_at = now
    if project.archived_at is None:
        project.archived_at = now
    db.commit()

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_DELETED",
        resource_type="project",
        resource_id=deleted_project_id,
        resource_name=deleted_project_name,
    )

    return {"message": "Project deleted"}
