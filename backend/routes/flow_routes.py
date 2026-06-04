from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.flow import Flow, FlowNode, FlowTransition
from models.chatbot import Chatbot
from models.flow_schema import BuilderContextResponse, FlowNodeCreate, FlowNodeResponse, FlowNodeUpdate, FlowResponse, FlowTransitionCreate, FlowTransitionResponse, FlowTransitionUpdate
from models.version import VersionChatbot
from services.auth import require_roles
from services.templates import create_starter_flow
import uuid

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/versions/{version_id}/flow", response_model=FlowResponse)
def get_flow(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    version = db.query(VersionChatbot).filter(VersionChatbot.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if not flow:
        flow = create_starter_flow(db, version_id, "blank")

    return flow


@router.get("/chatbots/{chatbot_id}/builder", response_model=BuilderContextResponse)
def get_chatbot_builder(
    chatbot_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")

    version = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == chatbot_id,
        VersionChatbot.status == "draft"
    ).order_by(VersionChatbot.version_number.desc()).first()

    if not version:
        version = db.query(VersionChatbot).filter(
            VersionChatbot.chatbot_id == chatbot_id
        ).order_by(VersionChatbot.version_number.desc()).first()

    if not version:
        raise HTTPException(status_code=404, detail="No version found for chatbot")

    flow = db.query(Flow).filter(Flow.version_id == version.id).first()
    if not flow:
        flow = create_starter_flow(db, version.id, "blank")

    return {
        "chatbot": {
            "id": chatbot.id,
            "name": chatbot.name,
            "description": chatbot.description,
            "purpose": chatbot.purpose,
            "mode": chatbot.mode,
            "channel": chatbot.channel
        },
        "version": {
            "id": version.id,
            "version_number": version.version_number,
            "status": version.status
        },
        "flow": flow
    }


@router.post("/flows/{flow_id}/nodes", response_model=FlowNodeResponse)
def create_node(
    flow_id: int,
    payload: FlowNodeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    node = FlowNode(
        flow_id=flow_id,
        node_key=f"{payload.type}_{uuid.uuid4().hex[:8]}",
        type=payload.type,
        label=payload.label,
        config=payload.config or {},
        position_x=payload.position_x,
        position_y=payload.position_y
    )

    db.add(node)
    db.commit()
    db.refresh(node)

    return node


@router.put("/flow-nodes/{node_id}", response_model=FlowNodeResponse)
def update_node(
    node_id: int,
    payload: FlowNodeUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    node = db.query(FlowNode).filter(FlowNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    if payload.label is not None:
        node.label = payload.label
    if payload.config is not None:
        node.config = payload.config
    if payload.position_x is not None:
        node.position_x = payload.position_x
    if payload.position_y is not None:
        node.position_y = payload.position_y

    db.commit()
    db.refresh(node)

    return node


@router.delete("/flow-nodes/{node_id}")
def delete_node(
    node_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    node = db.query(FlowNode).filter(FlowNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    db.query(FlowTransition).filter(
        FlowTransition.flow_id == node.flow_id,
        (
            (FlowTransition.source_node_key == node.node_key)
            | (FlowTransition.target_node_key == node.node_key)
        )
    ).delete(synchronize_session=False)
    db.delete(node)
    db.commit()

    return {"message": "Node deleted"}


@router.post("/flows/{flow_id}/transitions", response_model=FlowTransitionResponse)
def create_transition(
    flow_id: int,
    payload: FlowTransitionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    source = db.query(FlowNode).filter(
        FlowNode.flow_id == flow_id,
        FlowNode.node_key == payload.source_node_key
    ).first()
    target = db.query(FlowNode).filter(
        FlowNode.flow_id == flow_id,
        FlowNode.node_key == payload.target_node_key
    ).first()
    if not source or not target:
        raise HTTPException(status_code=400, detail="Source and target nodes must exist")

    transition = FlowTransition(
        flow_id=flow_id,
        source_node_key=payload.source_node_key,
        target_node_key=payload.target_node_key,
        label=payload.label,
        condition=payload.condition
    )
    db.add(transition)
    db.commit()
    db.refresh(transition)

    return transition


@router.put("/flow-transitions/{transition_id}", response_model=FlowTransitionResponse)
def update_transition(
    transition_id: int,
    payload: FlowTransitionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    transition = db.query(FlowTransition).filter(FlowTransition.id == transition_id).first()
    if not transition:
        raise HTTPException(status_code=404, detail="Transition not found")

    if payload.source_node_key is not None:
        transition.source_node_key = payload.source_node_key
    if payload.target_node_key is not None:
        transition.target_node_key = payload.target_node_key
    if payload.label is not None:
        transition.label = payload.label
    if payload.condition is not None:
        transition.condition = payload.condition

    db.commit()
    db.refresh(transition)

    return transition


@router.delete("/flow-transitions/{transition_id}")
def delete_transition(
    transition_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    transition = db.query(FlowTransition).filter(FlowTransition.id == transition_id).first()
    if not transition:
        raise HTTPException(status_code=404, detail="Transition not found")

    db.delete(transition)
    db.commit()

    return {"message": "Transition deleted"}
