from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from database.db import SessionLocal
from models.chatbot import Chatbot
from models.chunk import Chunk
from models.conversation import ConversationMessage, ConversationSession
from models.document import Document
from models.flow import Flow, FlowNode, FlowTransition
from models.knowledge_base import KnowledgeBase
from models.llm_config import LLMConfig
from models.project import Project
from models.project_schema import ProjectCreate, ProjectOverview, ProjectResponse, ProjectUpdate
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def project_query_for_user(db: Session, current_user: User):
    query = db.query(Project)
    if current_user.role == "manager":
        query = query.filter(Project.user_id == current_user.id)
    return query


def get_accessible_project(db: Session, project_id: int, current_user: User) -> Project:
    project = project_query_for_user(db, current_user).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def project_stats_for_ids(db: Session, project_ids: list[int]) -> dict[int, dict]:
    stats = {
        project_id: {
            "chatbot_count": 0,
            "version_count": 0,
            "published_version_count": 0,
            "draft_version_count": 0,
            "archived_version_count": 0,
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

    return stats


def serialize_project(project: Project, stats: dict | None = None) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "user_id": project.user_id,
        "created_at": project.created_at,
        **(stats or {
            "chatbot_count": 0,
            "version_count": 0,
            "published_version_count": 0,
            "draft_version_count": 0,
            "archived_version_count": 0,
        })
    }

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
        user_id=current_user.id
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    stats = project_stats_for_ids(db, [new_project.id])
    return serialize_project(new_project, stats.get(new_project.id))

@router.get("/projects", response_model=list[ProjectResponse])
def get_projects(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    query = project_query_for_user(db, current_user)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.name.ilike(term), Project.description.ilike(term)))

    projects = query.order_by(Project.created_at.desc()).offset(offset).limit(limit).all()
    stats = project_stats_for_ids(db, [project.id for project in projects])
    return [serialize_project(project, stats.get(project.id)) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectOverview)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    stats = project_stats_for_ids(db, [project.id])
    return serialize_project(project, stats.get(project.id))


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

    project.name = name
    project.description = payload.description.strip() or "No description"
    db.commit()
    db.refresh(project)

    stats = project_stats_for_ids(db, [project.id])
    return serialize_project(project, stats.get(project.id))


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)

    chatbots = db.query(Chatbot).filter(Chatbot.project_id == project_id).all()
    for chatbot in chatbots:
        chatbot.active_version_id = None
        db.commit()

        sessions = db.query(ConversationSession).filter(
            ConversationSession.chatbot_id == chatbot.id
        ).all()
        for session in sessions:
            db.query(ConversationMessage).filter(
                ConversationMessage.session_id == session.id
            ).delete()
            db.delete(session)
        db.commit()

        versions = db.query(VersionChatbot).filter(
            VersionChatbot.chatbot_id == chatbot.id
        ).all()
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

            config = db.query(LLMConfig).filter(
                LLMConfig.version_id == version.id
            ).first()
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

    db.delete(project)
    db.commit()

    return {"message": "Project deleted"}
