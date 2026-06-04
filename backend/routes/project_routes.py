from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
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


def project_stats(db: Session, project_id: int) -> dict:
    chatbot_count = db.query(Chatbot).filter(Chatbot.project_id == project_id).count()
    version_query = db.query(VersionChatbot).join(
        Chatbot,
        VersionChatbot.chatbot_id == Chatbot.id
    ).filter(Chatbot.project_id == project_id)

    return {
        "chatbot_count": chatbot_count,
        "version_count": version_query.count(),
        "published_version_count": version_query.filter(VersionChatbot.status == "published").count(),
        "draft_version_count": version_query.filter(VersionChatbot.status == "draft").count(),
        "archived_version_count": version_query.filter(VersionChatbot.status == "archived").count(),
    }


def serialize_project(db: Session, project: Project) -> dict:
    stats = project_stats(db, project.id)
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "user_id": project.user_id,
        "created_at": project.created_at,
        **stats
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

    return serialize_project(db, new_project)

@router.get("/projects", response_model=list[ProjectResponse])
def get_projects(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    query = project_query_for_user(db, current_user)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.name.ilike(term), Project.description.ilike(term)))

    projects = query.order_by(Project.created_at.desc()).all()
    return [serialize_project(db, project) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectOverview)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    project = get_accessible_project(db, project_id, current_user)
    return serialize_project(db, project)


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

    return serialize_project(db, project)


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
