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
from models.project_schema import ProjectCreate, ProjectOverview, ProjectResponse, ProjectSummaryResponse, ProjectUpdate
from models.runtime_log import RuntimeLog
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.audit import record_audit_log

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
            "assistant_count": 0,
            "active_assistant_count": 0,
            "published_assistant_count": 0,
            "draft_only_assistant_count": 0,
            "last_activity_at": None,
        })
    }


def project_summary_for_user(db: Session, current_user: User) -> ProjectSummaryResponse:
    project_ids = [project_id for (project_id,) in project_query_for_user(db, current_user).with_entities(Project.id).all()]
    stats = project_stats_for_ids(db, project_ids)
    return ProjectSummaryResponse(
        projects=len(project_ids),
        assistants=sum(item["assistant_count"] for item in stats.values()),
        published_assistants=sum(item["published_assistant_count"] for item in stats.values()),
        draft_only=sum(item["draft_only_assistant_count"] for item in stats.values()),
    )

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
    current_user: User = Depends(require_roles("admin", "manager"))
):
    query = project_query_for_user(db, current_user)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.name.ilike(term), Project.description.ilike(term)))

    projects = query.order_by(Project.created_at.desc()).offset(offset).limit(limit).all()
    stats = project_stats_for_ids(db, [project.id for project in projects])
    return [serialize_project(project, stats.get(project.id)) for project in projects]


@router.get("/projects/summary", response_model=ProjectSummaryResponse)
def get_projects_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    return project_summary_for_user(db, current_user)


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

    record_audit_log(
        db,
        actor=current_user,
        action="PROJECT_UPDATED",
        resource_type="project",
        resource_id=project.id,
        resource_name=project.name,
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

            knowledge_bases = db.query(KnowledgeBase).filter(
                KnowledgeBase.version_id == version.id
            ).all()
            knowledge_base_ids = [knowledge_base.id for knowledge_base in knowledge_bases]
            if knowledge_base_ids:
                document_ids = [
                    document_id for (document_id,) in db.query(Document.id).filter(
                        Document.knowledge_base_id.in_(knowledge_base_ids)
                    ).all()
                ]
                if document_ids:
                    db.query(Chunk).filter(Chunk.document_id.in_(document_ids)).delete(synchronize_session=False)
                    db.query(Document).filter(Document.id.in_(document_ids)).delete(synchronize_session=False)
                db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(knowledge_base_ids)).delete(synchronize_session=False)
                db.flush()

            db.delete(version)

        db.flush()
        db.delete(chatbot)

    db.delete(project)
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
