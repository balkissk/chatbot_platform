from copy import deepcopy
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
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
from models.user import User
from models.version import VersionChatbot
from models.version_schema import VersionCreate
from services.auth import require_roles
from services.flow_validation import validate_flow_version
from services.templates import create_starter_flow

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_accessible_chatbot(db: Session, chatbot_id: int, current_user: User) -> Chatbot:
    query = db.query(Chatbot).filter(Chatbot.id == chatbot_id)
    if current_user.role == "manager":
        query = query.join(Project, Chatbot.project_id == Project.id).filter(Project.user_id == current_user.id)

    chatbot = query.first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")

    return chatbot


def get_accessible_version(db: Session, version_id: int, current_user: User) -> VersionChatbot:
    version = db.query(VersionChatbot).filter(VersionChatbot.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    get_accessible_chatbot(db, version.chatbot_id, current_user)
    return version


def serialize_version(version: VersionChatbot, chatbot: Chatbot | None = None) -> dict:
    return {
        "id": version.id,
        "version_number": version.version_number,
        "status": version.status,
        "created_at": version.created_at,
        "published_at": version.published_at,
        "archived_at": version.archived_at,
        "chatbot_id": version.chatbot_id,
        "created_by": version.created_by,
        "published_by": version.published_by,
        "archived_by": version.archived_by,
        "duplicated_from_version_id": version.duplicated_from_version_id,
        "is_active": bool(chatbot and chatbot.active_version_id == version.id),
    }


def create_default_llm_config(db: Session, version_id: int) -> None:
    db.add(LLMConfig(
        version_id=version_id,
        model="llama3",
        temperature=0.7,
        system_prompt="You are a helpful assistant"
    ))
    db.commit()


def copy_llm_config(db: Session, source_version_id: int, target_version_id: int) -> None:
    source_config = db.query(LLMConfig).filter(LLMConfig.version_id == source_version_id).first()
    if not source_config:
        create_default_llm_config(db, target_version_id)
        return

    db.add(LLMConfig(
        version_id=target_version_id,
        model=source_config.model,
        temperature=source_config.temperature,
        system_prompt=source_config.system_prompt
    ))
    db.commit()


def copy_flow(db: Session, source_version_id: int, target_version_id: int) -> None:
    source_flow = db.query(Flow).filter(Flow.version_id == source_version_id).first()
    if not source_flow:
        create_starter_flow(db, target_version_id, "blank")
        return

    new_flow = Flow(version_id=target_version_id, name=source_flow.name)
    db.add(new_flow)
    db.commit()
    db.refresh(new_flow)

    nodes = db.query(FlowNode).filter(FlowNode.flow_id == source_flow.id).all()
    for node in nodes:
        db.add(FlowNode(
            flow_id=new_flow.id,
            node_key=node.node_key,
            type=node.type,
            label=node.label,
            config=deepcopy(node.config or {}),
            position_x=node.position_x,
            position_y=node.position_y
        ))

    transitions = db.query(FlowTransition).filter(FlowTransition.flow_id == source_flow.id).all()
    for transition in transitions:
        db.add(FlowTransition(
            flow_id=new_flow.id,
            source_node_key=transition.source_node_key,
            target_node_key=transition.target_node_key,
            label=transition.label,
            condition=transition.condition
        ))

    db.commit()


@router.post("/versions")
def create_version(
    version: VersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, version.chatbot_id, current_user)
    last_version = db.query(VersionChatbot) \
        .filter(VersionChatbot.chatbot_id == chatbot.id) \
        .order_by(VersionChatbot.version_number.desc()) \
        .first()

    new_number = 1 if not last_version else last_version.version_number + 1

    new_version = VersionChatbot(
        chatbot_id=chatbot.id,
        version_number=new_number,
        status="draft",
        created_by=current_user.id
    )

    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    create_default_llm_config(db, new_version.id)
    create_starter_flow(db, new_version.id, "blank")

    return serialize_version(new_version, chatbot)


@router.post("/versions/{version_id}/duplicate")
def duplicate_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    source_version = get_accessible_version(db, version_id, current_user)
    chatbot = get_accessible_chatbot(db, source_version.chatbot_id, current_user)
    last_version = db.query(VersionChatbot) \
        .filter(VersionChatbot.chatbot_id == chatbot.id) \
        .order_by(VersionChatbot.version_number.desc()) \
        .first()

    new_version = VersionChatbot(
        chatbot_id=chatbot.id,
        version_number=(1 if not last_version else last_version.version_number + 1),
        status="draft",
        created_by=current_user.id,
        duplicated_from_version_id=source_version.id
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    copy_llm_config(db, source_version.id, new_version.id)
    copy_flow(db, source_version.id, new_version.id)

    db.refresh(new_version)
    return serialize_version(new_version, chatbot)


@router.get("/chatbots/{chatbot_id}/versions")
def get_versions(
    chatbot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    chatbot = get_accessible_chatbot(db, chatbot_id, current_user)
    versions = db.query(VersionChatbot) \
        .filter(VersionChatbot.chatbot_id == chatbot.id) \
        .order_by(VersionChatbot.version_number.desc()) \
        .all()

    return [serialize_version(version, chatbot) for version in versions]


@router.put("/versions/{version_id}/publish")
def publish_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    version = get_accessible_version(db, version_id, current_user)
    chatbot = get_accessible_chatbot(db, version.chatbot_id, current_user)
    validation = validate_flow_version(db, version_id)
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Fix the flow validation errors before publishing.",
                "errors": validation["errors"]
            }
        )

    all_versions = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == version.chatbot_id
    ).all()

    now = datetime.utcnow()
    for item in all_versions:
        if item.id != version.id:
            item.status = "archived"
            item.archived_at = now
            item.archived_by = current_user.id

    version.status = "published"
    version.published_at = now
    version.published_by = current_user.id
    version.archived_at = None
    version.archived_by = None
    chatbot.active_version_id = version.id

    db.commit()
    db.refresh(version)
    db.refresh(chatbot)

    return {"message": "Version published", "version": serialize_version(version, chatbot)}


@router.put("/versions/{version_id}/archive")
def archive_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    version = get_accessible_version(db, version_id, current_user)
    chatbot = get_accessible_chatbot(db, version.chatbot_id, current_user)

    if chatbot.active_version_id == version.id:
        raise HTTPException(status_code=400, detail="Cannot archive the active version. Publish another version first.")

    version.status = "archived"
    version.archived_at = datetime.utcnow()
    version.archived_by = current_user.id

    db.commit()
    db.refresh(version)

    return {"message": "Version archived", "version": serialize_version(version, chatbot)}


@router.delete("/versions/{version_id}")
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    version = get_accessible_version(db, version_id, current_user)
    chatbot = get_accessible_chatbot(db, version.chatbot_id, current_user)

    if chatbot.active_version_id == version.id or version.status == "published":
        raise HTTPException(status_code=400, detail="Cannot delete the active or published version. Publish another version first.")

    version_count = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == version.chatbot_id
    ).count()
    if version_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last version of a chatbot.")

    sessions = db.query(ConversationSession).filter(
        ConversationSession.version_id == version.id
    ).all()
    for session in sessions:
        db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session.id
        ).delete()
        db.delete(session)
    db.commit()

    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if flow:
        db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
        db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
        db.delete(flow)

    config = db.query(LLMConfig).filter(LLMConfig.version_id == version_id).first()
    if config:
        db.delete(config)

    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.version_id == version_id
    ).first()
    if knowledge_base:
        documents = db.query(Document).filter(
            Document.knowledge_base_id == knowledge_base.id
        ).all()
        for document in documents:
            db.query(Chunk).filter(Chunk.document_id == document.id).delete()
            db.delete(document)
        db.delete(knowledge_base)

    db.query(VersionChatbot).filter(
        VersionChatbot.duplicated_from_version_id == version.id
    ).update({VersionChatbot.duplicated_from_version_id: None}, synchronize_session=False)

    db.delete(version)
    db.commit()

    return {"message": "Version deleted"}
