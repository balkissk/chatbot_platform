import secrets

from fastapi import APIRouter, Depends, HTTPException
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


def serialize_chatbot(chatbot: Chatbot) -> dict:
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
        "project_id": chatbot.project_id
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
    for chatbot in chatbots:
        ensure_public_api_key(db, chatbot)
    return [serialize_chatbot(chatbot) for chatbot in chatbots]


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
    for chatbot in chatbots:
        ensure_public_api_key(db, chatbot)
    return [serialize_chatbot(chatbot) for chatbot in chatbots]
