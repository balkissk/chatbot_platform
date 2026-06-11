import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from database.db import SessionLocal
from models.chatbot import Chatbot
from models.chatbot_schema import ChatbotApiKeyResponse, ChatbotCreate, ChatbotStatusUpdate, ChatbotUpdate, RagSettingsUpdate
from models.chunk import Chunk
from models.conversation import ConversationMessage, ConversationSession
from models.document import Document
from models.flow import Flow, FlowNode, FlowTransition
from models.knowledge_base import KnowledgeBase
from models.llm_config import LLMConfig
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.rag_settings import normalize_rag_settings
from services.templates import create_starter_flow

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_project_access(db: Session, project_id: int, current_user: User) -> Project:
    query = db.query(Project).filter(Project.id == project_id)
    if current_user.role == "manager":
        query = query.filter(Project.user_id == current_user.id)

    project = query.first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


def get_accessible_chatbot(db: Session, chatbot_id: int, current_user: User) -> Chatbot:
    chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")

    ensure_project_access(db, chatbot.project_id, current_user)
    return chatbot


def new_public_api_key() -> str:
    return f"cp_{secrets.token_urlsafe(32)}"


def ensure_public_api_key(db: Session, chatbot: Chatbot) -> str:
    if not chatbot.public_api_key:
        chatbot.public_api_key = new_public_api_key()
        if chatbot.public_api_enabled is None:
            chatbot.public_api_enabled = True
        db.commit()
        db.refresh(chatbot)
    return chatbot.public_api_key


def ensure_public_api_keys(db: Session, chatbots: list[Chatbot]) -> None:
    changed = False
    for chatbot in chatbots:
        if not chatbot.public_api_key:
            chatbot.public_api_key = new_public_api_key()
            if chatbot.public_api_enabled is None:
                chatbot.public_api_enabled = True
            changed = True

    if changed:
        db.commit()
        for chatbot in chatbots:
            db.refresh(chatbot)


def chatbot_version_stats_for_ids(db: Session, chatbot_ids: list[int]) -> dict[int, dict]:
    stats = {
        chatbot_id: {
            "version_count": 0,
            "published_version_count": 0,
            "draft_version_count": 0,
            "archived_version_count": 0,
        }
        for chatbot_id in chatbot_ids
    }
    if not chatbot_ids:
        return stats

    rows = db.query(
        VersionChatbot.chatbot_id,
        VersionChatbot.status,
        func.count(VersionChatbot.id)
    ).filter(
        VersionChatbot.chatbot_id.in_(chatbot_ids)
    ).group_by(
        VersionChatbot.chatbot_id,
        VersionChatbot.status
    ).all()

    for chatbot_id, status, count in rows:
        row = stats.setdefault(chatbot_id, {
            "version_count": 0,
            "published_version_count": 0,
            "draft_version_count": 0,
            "archived_version_count": 0,
        })
        row["version_count"] += count
        if status == "published":
            row["published_version_count"] = count
        elif status == "draft":
            row["draft_version_count"] = count
        elif status == "archived":
            row["archived_version_count"] = count

    return stats


def serialize_chatbot(chatbot: Chatbot, stats: dict | None = None) -> dict:
    return {
        "id": chatbot.id,
        "name": chatbot.name,
        "description": chatbot.description,
        "language": chatbot.language,
        "type": chatbot.type,
        "purpose": chatbot.purpose,
        "mode": chatbot.mode,
        "channel": chatbot.channel,
        "build_method": chatbot.build_method,
        "template_key": chatbot.template_key,
        "is_active": chatbot.is_active,
        "active_version_id": chatbot.active_version_id,
        "public_api_key": chatbot.public_api_key,
        "public_api_enabled": chatbot.public_api_enabled,
        "rag_settings": normalize_rag_settings(chatbot.rag_settings),
        "created_at": chatbot.created_at,
        "project_id": chatbot.project_id,
        **(stats or {
            "version_count": 0,
            "published_version_count": 0,
            "draft_version_count": 0,
            "archived_version_count": 0,
        })
    }


def serialize_chatbot_details(db: Session, chatbot: Chatbot) -> dict:
    project = db.query(Project).filter(Project.id == chatbot.project_id).first()
    versions = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == chatbot.id
    ).order_by(VersionChatbot.version_number.desc()).all()

    return {
        **serialize_chatbot(chatbot),
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description
        } if project else None,
        "versions": [
            {
                "id": version.id,
                "version_number": version.version_number,
                "status": version.status,
                "created_at": version.created_at,
                "published_at": version.published_at,
                "archived_at": version.archived_at,
                "duplicated_from_version_id": version.duplicated_from_version_id,
                "is_active": chatbot.active_version_id == version.id
            }
            for version in versions
        ]
    }


def serialize_conversation_session(db: Session, session: ConversationSession) -> dict:
    message_count = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).count()
    messages = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).order_by(ConversationMessage.created_at.asc()).all()
    last_message = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).order_by(ConversationMessage.created_at.desc()).first()
    variables = session.variables or {}

    return {
        "id": session.id,
        "chatbot_id": session.chatbot_id,
        "version_id": session.version_id,
        "user_id": session.user_id,
        "channel": session_channel(session),
        "feedback_status": session_feedback_status(session),
        "response_type": session_response_type(messages),
        "current_node_key": session.current_node_key,
        "message_count": message_count,
        "last_message": last_message.content if last_message else "",
        "last_user_message": next((message.content for message in reversed(messages) if message.role == "user"), ""),
        "last_bot_message": next((message.content for message in reversed(messages) if message.role == "bot"), ""),
        "feedback_at": variables.get("__feedback_at"),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def messages_by_session(db: Session, session_ids: list[int], per_session_limit: int | None = None) -> dict[int, list[ConversationMessage]]:
    if not session_ids:
        return {}

    rows = db.query(ConversationMessage).filter(
        ConversationMessage.session_id.in_(session_ids)
    ).order_by(ConversationMessage.session_id.asc(), ConversationMessage.created_at.asc()).all()

    grouped: dict[int, list[ConversationMessage]] = defaultdict(list)
    for message in rows:
        if per_session_limit and len(grouped[message.session_id]) >= per_session_limit:
            continue
        grouped[message.session_id].append(message)
    return grouped


def serialize_conversation_summary(session: ConversationSession, messages: list[ConversationMessage]) -> dict:
    variables = session.variables or {}
    last_message = messages[-1] if messages else None

    return {
        "id": session.id,
        "chatbot_id": session.chatbot_id,
        "version_id": session.version_id,
        "user_id": session.user_id,
        "channel": session_channel(session),
        "feedback_status": session_feedback_status(session),
        "response_type": session_response_type(messages),
        "current_node_key": session.current_node_key,
        "message_count": len(messages),
        "last_message": last_message.content if last_message else "",
        "last_user_message": next((message.content for message in reversed(messages) if message.role == "user"), ""),
        "last_bot_message": next((message.content for message in reversed(messages) if message.role == "bot"), ""),
        "feedback_at": variables.get("__feedback_at"),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def date_series(days: int = 14) -> list[datetime.date]:
    today = datetime.utcnow().date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def top_keywords(messages: list[ConversationMessage], limit: int = 8) -> list[dict]:
    stopwords = {
        "the", "and", "for", "you", "your", "with", "that", "this", "from", "what",
        "how", "can", "are", "was", "were", "une", "des", "les", "est", "pour",
        "dans", "avec", "sur", "qui", "que", "quoi", "comment", "vous", "nous"
    }
    words = Counter()
    for message in messages:
        if message.role != "user":
            continue
        for raw_word in (message.content or "").lower().replace("?", " ").replace(".", " ").split():
            word = raw_word.strip(",:;!()[]{}\"'")
            if len(word) >= 4 and word not in stopwords:
                words[word] += 1

    return [
        {"topic": topic, "count": count}
        for topic, count in words.most_common(limit)
    ]


def used_buttons(messages: list[ConversationMessage], limit: int = 8) -> list[dict]:
    counts = Counter()
    for message in messages:
        for option in message.options or []:
            if option:
                counts[str(option)] += 1

    return [
        {"label": label, "count": count}
        for label, count in counts.most_common(limit)
    ]


def session_channel(session: ConversationSession) -> str:
    variables = session.variables or {}
    channel = str(variables.get("__channel") or "").strip().lower()
    if channel in {"public", "dashboard", "widget"}:
        return channel
    return "dashboard" if session.user_id else "public"


def session_feedback_status(session: ConversationSession) -> str:
    feedback = str((session.variables or {}).get("__feedback") or "").strip().lower()
    if feedback == "helpful":
        return "positive"
    if feedback == "not_helpful":
        return "negative"
    return "no_feedback"


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


def session_response_type(messages: list[ConversationMessage]) -> str:
    modes = {message_response_mode(message) for message in messages if message.role == "bot"}
    if "fallback" in modes:
        return "fallback"
    if "ai_rag" in modes:
        return "ai_rag"
    if "flow" in modes:
        return "flow"
    return "unknown"


def unanswered_question_rows(db: Session, chatbot_id: int) -> list[dict]:
    sessions = db.query(ConversationSession).filter(
        ConversationSession.chatbot_id == chatbot_id
    ).order_by(ConversationSession.updated_at.desc()).limit(300).all()
    grouped_messages = messages_by_session(db, [session.id for session in sessions])
    grouped: dict[str, dict] = {}

    for session in sessions:
        messages = grouped_messages.get(session.id, [])

        previous_user = None
        for message in messages:
            if message.role == "user":
                previous_user = message
                continue
            if message.role != "bot" or message_response_mode(message) != "fallback" or not previous_user:
                continue

            question = (previous_user.content or "").strip()
            if not question:
                continue
            key = " ".join(question.lower().split())
            row = grouped.setdefault(key, {
                "question": question,
                "count": 0,
                "last_asked_at": previous_user.created_at,
                "session_id": session.id
            })
            row["count"] += 1
            if previous_user.created_at and previous_user.created_at >= row["last_asked_at"]:
                row["last_asked_at"] = previous_user.created_at
                row["session_id"] = session.id

    return sorted(grouped.values(), key=lambda item: (item["count"], item["last_asked_at"]), reverse=True)[:25]

@router.post("/chatbots")
def create_chatbot(
    chatbot: ChatbotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    ensure_project_access(db, chatbot.project_id, current_user)
    name = chatbot.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Chatbot name is required")

    new_chatbot = Chatbot(
        name=name,
        description=(chatbot.description or "").strip(),
        language=chatbot.language,
        type=chatbot.type,
        purpose=chatbot.purpose,
        mode=chatbot.mode,
        channel=chatbot.channel,
        build_method=chatbot.build_method,
        template_key=chatbot.template_key,
        public_api_key=new_public_api_key(),
        public_api_enabled=True,
        project_id=chatbot.project_id
    )

    db.add(new_chatbot)
    db.commit()
    db.refresh(new_chatbot)

    first_version = VersionChatbot(
        chatbot_id=new_chatbot.id,
        version_number=1,
        status="draft",
        created_by=current_user.id
    )
    db.add(first_version)
    db.commit()
    db.refresh(first_version)

    db.add(LLMConfig(
        version_id=first_version.id,
        model="phi3",
        temperature=0.7,
        system_prompt="You are a helpful assistant"
    ))
    db.commit()
    create_starter_flow(db, first_version.id, "blank")

    return serialize_chatbot(new_chatbot)

@router.get("/chatbots")
def get_chatbots(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    query = db.query(Chatbot)
    if current_user.role == "manager":
        query = query.join(Project, Chatbot.project_id == Project.id).filter(Project.user_id == current_user.id)
    chatbots = query.all()
    ensure_public_api_keys(db, chatbots)
    version_stats = chatbot_version_stats_for_ids(db, [chatbot.id for chatbot in chatbots])
    return [serialize_chatbot(chatbot, version_stats.get(chatbot.id)) for chatbot in chatbots]


@router.get("/chatbots/{id}/analytics")
def get_chatbot_analytics(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    sessions = db.query(ConversationSession).filter(
        ConversationSession.chatbot_id == chatbot.id
    ).all()
    session_ids = [session.id for session in sessions]
    total_messages = db.query(ConversationMessage).filter(
        ConversationMessage.session_id.in_(session_ids)
    ).count() if session_ids else 0
    messages = db.query(ConversationMessage).filter(
        ConversationMessage.session_id.in_(session_ids)
    ).order_by(ConversationMessage.created_at.desc()).limit(1000).all() if session_ids else []

    version_ids = [
        row.id for row in db.query(VersionChatbot.id).filter(
            VersionChatbot.chatbot_id == chatbot.id
        ).all()
    ]
    knowledge_base_ids = [
        row.id for row in db.query(KnowledgeBase.id).filter(
            KnowledgeBase.version_id.in_(version_ids)
        ).all()
    ] if version_ids else []
    document_ids = [
        row.id for row in db.query(Document.id).filter(
            Document.knowledge_base_id.in_(knowledge_base_ids)
        ).all()
    ] if knowledge_base_ids else []

    ready_embeddings = db.query(Chunk).filter(
        Chunk.document_id.in_(document_ids),
        Chunk.embedding_status == "ready"
    ).count() if document_ids else 0

    session_counts = Counter(session.created_at.date() for session in sessions if session.created_at)
    message_counts = Counter(message.created_at.date() for message in messages if message.created_at)
    days = date_series()

    positive_feedback = sum(
        1 for session in sessions
        if (session.variables or {}).get("__feedback") == "helpful"
    )
    negative_feedback = sum(
        1 for session in sessions
        if (session.variables or {}).get("__feedback") == "not_helpful"
    )
    total_feedback = positive_feedback + negative_feedback
    recent_sessions = sorted(
        sessions,
        key=lambda item: item.updated_at or item.created_at,
        reverse=True
    )[:8]
    recent_messages = messages_by_session(db, [session.id for session in recent_sessions])

    return {
        "chatbot": serialize_chatbot(chatbot),
        "kpis": {
            "total_conversations": len(sessions),
            "total_messages": total_messages,
            "total_documents": len(document_ids),
            "average_response_time_ms": 0,
            "positive_feedback_percent": round((positive_feedback / total_feedback) * 100, 1) if total_feedback else 0,
            "negative_feedback_percent": round((negative_feedback / total_feedback) * 100, 1) if total_feedback else 0,
            "total_chunks": db.query(Chunk).filter(Chunk.document_id.in_(document_ids)).count() if document_ids else 0,
            "total_embeddings": ready_embeddings
        },
        "conversations_over_time": [
            {"date": day.isoformat(), "count": session_counts.get(day, 0)}
            for day in days
        ],
        "messages_over_time": [
            {"date": day.isoformat(), "count": message_counts.get(day, 0)}
            for day in days
        ],
        "top_topics": top_keywords(messages),
        "most_used_buttons": used_buttons(messages),
        "recent_conversations": [
            serialize_conversation_summary(session, recent_messages.get(session.id, []))
            for session in recent_sessions
        ]
    }


@router.get("/chatbots/{id}/conversations")
def get_chatbot_conversations(
    id: int,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    channel: str | None = None,
    feedback: str | None = None,
    response_type: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    query = db.query(ConversationSession).filter(ConversationSession.chatbot_id == chatbot.id)

    if date_from:
        query = query.filter(ConversationSession.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        end_date = datetime.fromisoformat(date_to) + timedelta(days=1)
        query = query.filter(ConversationSession.created_at < end_date)

    if search:
        needle = search.strip()
        if needle:
            message_session_ids = [
                row.session_id for row in db.query(ConversationMessage.session_id).filter(
                    ConversationMessage.content.ilike(f"%{needle}%")
                ).distinct().limit(1000).all()
            ]
            matching_ids = set(message_session_ids)
            if needle.isdigit():
                matching_ids.add(int(needle))
            if not matching_ids:
                return []
            query = query.filter(ConversationSession.id.in_(matching_ids))

    uses_derived_filters = bool(channel or feedback or response_type)
    if uses_derived_filters:
        candidate_limit = min(max(offset + (limit * 4), limit), 500)
        sessions = query.order_by(ConversationSession.updated_at.desc()).limit(candidate_limit).all()
    else:
        sessions = query.order_by(ConversationSession.updated_at.desc()).offset(offset).limit(limit).all()

    grouped_messages = messages_by_session(db, [session.id for session in sessions])

    if channel:
        sessions = [session for session in sessions if session_channel(session) == channel]
    if feedback:
        sessions = [session for session in sessions if session_feedback_status(session) == feedback]
    if response_type:
        sessions = [
            session for session in sessions
            if session_response_type(grouped_messages.get(session.id, [])) == response_type
        ]

    if uses_derived_filters:
        sessions = sessions[offset:offset + limit]

    return [
        serialize_conversation_summary(session, grouped_messages.get(session.id, []))
        for session in sessions
    ]


@router.get("/chatbots/{id}/conversations/unanswered")
def get_chatbot_unanswered_questions(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    return unanswered_question_rows(db, chatbot.id)


@router.get("/chatbots/{id}/conversations/{session_id}")
def get_chatbot_conversation_details(
    id: int,
    session_id: int,
    message_limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    session = db.query(ConversationSession).filter(
        ConversationSession.id == session_id,
        ConversationSession.chatbot_id == chatbot.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session.id
    ).order_by(ConversationMessage.created_at.asc()).limit(message_limit).all()

    return {
        **serialize_conversation_summary(session, messages),
        "variables": session.variables or {},
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "response_mode": message_response_mode(message),
                "options": message.options or [],
                "sources": message.sources or [],
                "created_at": message.created_at
            }
            for message in messages
        ]
    }


@router.get("/chatbots/{id}")
def get_chatbot_details(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    ensure_public_api_key(db, chatbot)
    return serialize_chatbot_details(db, chatbot)


@router.put("/chatbots/{id}/api-key/regenerate", response_model=ChatbotApiKeyResponse)
def regenerate_chatbot_api_key(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    chatbot.public_api_key = new_public_api_key()
    chatbot.public_api_enabled = True
    db.commit()
    db.refresh(chatbot)
    return {"public_api_key": chatbot.public_api_key}


@router.get("/chatbots/{id}/rag-settings")
def get_chatbot_rag_settings(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    return normalize_rag_settings(chatbot.rag_settings)


@router.put("/chatbots/{id}/rag-settings")
def update_chatbot_rag_settings(
    id: int,
    payload: RagSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    chatbot.rag_settings = normalize_rag_settings(payload.model_dump())
    db.commit()
    db.refresh(chatbot)
    return normalize_rag_settings(chatbot.rag_settings)


@router.put("/chatbots/{id}")
def update_chatbot(
    id: int,
    payload: ChatbotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    name = payload.name.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Chatbot name is required")

    chatbot.name = name
    chatbot.description = (payload.description or "").strip()
    chatbot.language = payload.language
    chatbot.type = payload.type
    chatbot.purpose = payload.purpose
    chatbot.mode = payload.mode
    chatbot.channel = payload.channel
    chatbot.template_key = payload.template_key

    db.commit()
    db.refresh(chatbot)

    return serialize_chatbot(chatbot)


@router.put("/chatbots/{id}/status")
def update_chatbot_status(
    id: int,
    payload: ChatbotStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    chatbot.is_active = payload.is_active
    db.commit()
    db.refresh(chatbot)

    return serialize_chatbot(chatbot)

@router.delete("/chatbots/{id}")
def delete_chatbot(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, id, current_user)
    chatbot.active_version_id = None
    db.commit()

    sessions = db.query(ConversationSession).filter(
        ConversationSession.chatbot_id == id
    ).all()
    for session in sessions:
        db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session.id
        ).delete()
        db.delete(session)
    db.commit()

    versions = db.query(VersionChatbot).filter(VersionChatbot.chatbot_id == id).all()
    version_ids = [version.id for version in versions]
    if version_ids:
        db.query(VersionChatbot).filter(
            VersionChatbot.duplicated_from_version_id.in_(version_ids)
        ).update({VersionChatbot.duplicated_from_version_id: None}, synchronize_session=False)
        db.commit()

    for version in versions:
        flow = db.query(Flow).filter(Flow.version_id == version.id).first()
        if flow:
            db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
            db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
            db.delete(flow)

        config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
        if config:
            db.delete(config)

        knowledge_base = db.query(KnowledgeBase).filter(
            KnowledgeBase.version_id == version.id
        ).first()
        if knowledge_base:
            documents = db.query(Document).filter(
                Document.knowledge_base_id == knowledge_base.id
            ).all()
            for document in documents:
                db.query(Chunk).filter(Chunk.document_id == document.id).delete()
                db.delete(document)
            db.delete(knowledge_base)

        db.delete(version)

    db.flush()
    db.delete(chatbot)
    db.commit()

    return {"message": "deleted"}
@router.get("/projects/{project_id}/chatbots")
def get_chatbots_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    ensure_project_access(db, project_id, current_user)
    chatbots = db.query(Chatbot).filter(Chatbot.project_id == project_id).all()
    ensure_public_api_keys(db, chatbots)
    version_stats = chatbot_version_stats_for_ids(db, [chatbot.id for chatbot in chatbots])
    return [serialize_chatbot(chatbot, version_stats.get(chatbot.id)) for chatbot in chatbots]
