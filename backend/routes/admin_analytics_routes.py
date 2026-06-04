from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot import Chatbot
from models.conversation import ConversationMessage, ConversationSession
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles

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


@router.get("/overview")
def analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    today_start = datetime.combine(datetime.utcnow().date(), time.min)

    total_projects = db.query(Project).count()
    total_chatbots = db.query(Chatbot).count()
    active_chatbots = db.query(Chatbot).filter(Chatbot.is_active.is_(True)).count()
    published_versions = db.query(VersionChatbot).filter(VersionChatbot.status == "published").count()
    total_sessions = db.query(ConversationSession).count()
    total_messages = db.query(ConversationMessage).count()
    sessions_today = db.query(ConversationSession).filter(
        ConversationSession.created_at >= today_start
    ).count()
    messages_today = db.query(ConversationMessage).filter(
        ConversationMessage.created_at >= today_start
    ).count()

    top_chatbots = db.query(
        Chatbot.id,
        Chatbot.name,
        func.count(ConversationSession.id).label("conversation_count")
    ).outerjoin(
        ConversationSession,
        ConversationSession.chatbot_id == Chatbot.id
    ).group_by(Chatbot.id, Chatbot.name).order_by(func.count(ConversationSession.id).desc()).limit(5).all()

    recent_sessions = db.query(ConversationSession).order_by(
        ConversationSession.updated_at.desc()
    ).limit(8).all()

    return {
        "total_projects": total_projects,
        "total_chatbots": total_chatbots,
        "active_chatbots": active_chatbots,
        "published_versions": published_versions,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "sessions_today": sessions_today,
        "messages_today": messages_today,
        "top_chatbots": [
            {
                "chatbot_id": row.id,
                "chatbot_name": row.name,
                "conversation_count": row.conversation_count
            }
            for row in top_chatbots
        ],
        "recent_sessions": [serialize_session(db, session) for session in recent_sessions]
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
