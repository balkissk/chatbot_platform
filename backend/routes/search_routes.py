from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot import Chatbot
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from routes.project_routes import project_query_for_user
from services.auth import require_roles

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def accessible_chatbot_query(db: Session, current_user: User):
    query = db.query(Chatbot).join(Project, Chatbot.project_id == Project.id).filter(Project.deleted_at.is_(None))
    if current_user.role == "manager":
        query = query.filter(Project.user_id == current_user.id)
    return query


@router.get("/search")
def global_search(
    q: str = Query(min_length=1),
    limit: int = Query(default=6, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    term = f"%{q.strip()}%"
    if not q.strip():
        return {"results": []}

    project_rows = (
        project_query_for_user(db, current_user)
        .filter(or_(Project.name.ilike(term), Project.description.ilike(term)))
        .order_by(func.lower(Project.name).asc())
        .limit(limit)
        .all()
    )
    project_results = [
        {
            "type": "Project",
            "id": project.id,
            "title": project.name,
            "subtitle": project.description or "Project workspace",
            "route": ["/dashboard/projects", project.id],
        }
        for project in project_rows
    ]

    chatbot_rows = (
        accessible_chatbot_query(db, current_user)
        .filter(or_(Chatbot.name.ilike(term), Chatbot.description.ilike(term)))
        .order_by(func.lower(Chatbot.name).asc())
        .limit(limit)
        .all()
    )
    chatbot_results = [
        {
            "type": "Assistant",
            "id": chatbot.id,
            "title": chatbot.name,
            "subtitle": chatbot.description or "Assistant",
            "route": ["/dashboard/projects", chatbot.project_id, "chatbots", chatbot.id],
        }
        for chatbot in chatbot_rows
    ]

    knowledge_rows = (
        db.query(KnowledgeBase, Chatbot, Project)
        .join(VersionChatbot, KnowledgeBase.version_id == VersionChatbot.id)
        .join(Chatbot, VersionChatbot.chatbot_id == Chatbot.id)
        .join(Project, Chatbot.project_id == Project.id)
        .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
        .filter(Project.deleted_at.is_(None))
        .filter(or_(KnowledgeBase.name.ilike(term), Document.filename.ilike(term)))
    )
    if current_user.role == "manager":
        knowledge_rows = knowledge_rows.filter(Project.user_id == current_user.id)

    seen_knowledge_ids: set[int] = set()
    knowledge_results = []
    for knowledge_base, chatbot, project in (
        knowledge_rows
        .order_by(func.lower(KnowledgeBase.name).asc())
        .limit(limit * 3)
        .all()
    ):
        if knowledge_base.id in seen_knowledge_ids:
            continue
        seen_knowledge_ids.add(knowledge_base.id)
        knowledge_results.append({
            "type": "Knowledge Base",
            "id": knowledge_base.id,
            "title": knowledge_base.name or f"{chatbot.name} knowledge",
            "subtitle": f"{chatbot.name} · {project.name}",
            "route": ["/dashboard/projects", project.id, "chatbots", chatbot.id, "knowledge"],
        })
        if len(knowledge_results) >= limit:
            break

    return {"results": [*project_results, *chatbot_results, *knowledge_results]}
