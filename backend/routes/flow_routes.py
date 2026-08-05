import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.flow import Flow, FlowNode, FlowTransition
from models.flow_template import FlowTemplate, FlowTemplateRevision
from models.chatbot import Chatbot
from models.chatbot_schema import safe_chatbot_language
from models.flow_schema import BuilderContextResponse, FlowNodeCreate, FlowNodeResponse, FlowNodeUpdate, FlowResponse, FlowTransitionCreate, FlowTransitionResponse, FlowTransitionUpdate
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.ai_provider import AIProviderError, generate_chat_completion
from services.flow_limits import (
    MAX_FLOW_NODES,
    MAX_FLOW_TRANSITIONS,
    is_valid_canvas_position,
    normalize_transition_output_key,
)
from services.flow_validation import validate_flow_version
from services.flow_runtime import execute_flow
from services.generated_flow import ensure_generated_flow_is_valid
from services.templates import TEMPLATES, create_starter_flow, replace_flow_with_template, template_generated_payload, template_metadata, template_options
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)


class FlowTemplateApply(BaseModel):
    template_key: str
    purpose: str | None = None
    template_revision: int | None = None


class FlowTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    purpose: str = "custom"
    is_exposed: bool = False
    is_shared: bool = False
    change_note: str | None = None


class FlowTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    purpose: str | None = None
    is_exposed: bool | None = None
    is_shared: bool | None = None
    test_scenarios: list[dict] | None = None


class FlowTemplateTestRun(BaseModel):
    name: str | None = None
    messages: list[str] | None = None
    expected_variables: dict | None = None
    expected_final_node_key: str | None = None


class FlowTemplateRevisionCreate(BaseModel):
    change_note: str | None = None


class AiGenerateRequest(BaseModel):
    assistant_goal: str
    business_context: str
    knowledge_base_description: str | None = None
    assistant_type: str | None = None
    language: str | None = None


class AiGeneratedNode(BaseModel):
    key: str
    type: str
    label: str
    config: dict
    position_x: int
    position_y: int


class AiGeneratedTransition(BaseModel):
    source_node_key: str
    target_node_key: str
    label: str | None = None
    condition: str | None = None


class AiGenerateResponse(BaseModel):
    assistant_name: str
    assistant_description: str
    welcome_message: str
    recommended_template: str
    detected_domain: str
    detected_intents: list[str]
    recommended_flow_type: str
    generated_nodes: list[dict]
    generated_edges: list[dict]
    suggested_variables: list[str]
    suggested_kb_categories: list[str]
    suggested_advanced_blocks: list[str]
    generation_confidence: float
    generation_explanation: str
    initial_flow_structure: dict


VISIBLE_TEMPLATE_BLOCK_TYPES = {
    "message",
    "question",
    "buttons",
    "end",
    "rag_answer",
    "knowledge_search",
    "collect_name",
    "collect_email",
    "collect_phone",
    "condition",
    "set_variable",
    "meeting_scheduler",
    "handoff",
}

HIDDEN_TEMPLATE_BLOCK_TYPES = {
    "api_request",
    "ai_router",
    "ai_classifier",
    "confidence_check",
    "lead_score",
    "action",
}


def _template_issue(severity: str, message: str, node_key: str | None = None) -> dict:
    return {
        "severity": severity,
        "message": message,
        "node_key": node_key,
    }


def _template_config_value(config: dict, key: str) -> str:
    return str((config or {}).get(key) or "").strip()


def _template_buttons(config: dict) -> list[str]:
    buttons = (config or {}).get("buttons") or []
    return [str(item).strip() for item in buttons if str(item).strip()] if isinstance(buttons, list) else []


def analyze_template_quality(template_key: str, template: dict) -> dict:
    nodes = template.get("nodes") or []
    transitions = template.get("transitions") or []
    issues: list[dict] = []
    node_keys = [str(node[0]) for node in nodes]
    node_key_set = set(node_keys)
    block_types: dict[str, int] = {}
    hidden_blocks: list[str] = []
    unsupported_blocks: list[str] = []

    if not nodes:
        issues.append(_template_issue("error", "Template has no blocks."))

    if len(node_keys) != len(node_key_set):
        issues.append(_template_issue("error", "Template has duplicate block keys."))

    if "start" not in node_key_set:
        issues.append(_template_issue("error", "Template has no start block."))

    for node_key, node_type, label, config, x, y in nodes:
        block_types[node_type] = block_types.get(node_type, 0) + 1
        if node_type in HIDDEN_TEMPLATE_BLOCK_TYPES:
            hidden_blocks.append(node_type)
            issues.append(_template_issue("warning", f"Uses hidden or legacy block type '{node_type}'.", node_key))
        elif node_type not in VISIBLE_TEMPLATE_BLOCK_TYPES:
            unsupported_blocks.append(node_type)
            issues.append(_template_issue("error", f"Unsupported block type '{node_type}'.", node_key))

        if not str(label or "").strip():
            issues.append(_template_issue("warning", "Block has no readable label.", node_key))
        if not is_valid_canvas_position(x) or not is_valid_canvas_position(y):
            issues.append(_template_issue("error", "Block position is outside supported canvas bounds.", node_key))

        config = config or {}
        if node_type == "message" and not _template_config_value(config, "text"):
            issues.append(_template_issue("error", "Message block is missing text.", node_key))
        if node_type in {"question", "collect_name", "collect_email", "collect_phone", "meeting_scheduler"}:
            if not _template_config_value(config, "prompt"):
                issues.append(_template_issue("error", "Input block is missing a prompt.", node_key))
            if not _template_config_value(config, "field"):
                issues.append(_template_issue("error", "Input block is missing a variable name.", node_key))
        if node_type == "buttons":
            buttons = _template_buttons(config)
            if not buttons:
                issues.append(_template_issue("error", "Buttons block has no options.", node_key))
            for button in buttons:
                if not any(source == node_key and label == button for source, _target, label, _condition in transitions):
                    issues.append(_template_issue("error", f"Button '{button}' has no matching path.", node_key))
        if node_type == "condition":
            if not _template_config_value(config, "field"):
                issues.append(_template_issue("error", "Condition is missing the variable to check.", node_key))
            labels = {str(label or "").lower() for source, _target, label, _condition in transitions if source == node_key}
            if "true" not in labels:
                issues.append(_template_issue("error", "Condition is missing a true path.", node_key))
            if "false" not in labels:
                issues.append(_template_issue("error", "Condition is missing a false path.", node_key))
        if node_type in {"rag_answer", "knowledge_search"} and not _template_config_value(config, "fallback"):
            issues.append(_template_issue("warning", "AI/RAG block has no fallback message.", node_key))
        if node_type == "end" and not _template_config_value(config, "message"):
            issues.append(_template_issue("warning", "End block has no closing message.", node_key))

    seen_transitions: set[tuple[str, str, str]] = set()
    for source, target, label, condition in transitions:
        if source not in node_key_set:
            issues.append(_template_issue("error", f"Connector starts from unknown block '{source}'."))
        if target not in node_key_set:
            issues.append(_template_issue("error", f"Connector points to unknown block '{target}'."))
        key = (str(source), str(target), normalize_transition_output_key(label, condition))
        if key in seen_transitions:
            issues.append(_template_issue("error", "Duplicate connector with same source, target and output key."))
        seen_transitions.add(key)

    severity_rank = {"error": 2, "warning": 1}
    max_severity = max((severity_rank.get(issue["severity"], 0) for issue in issues), default=0)
    status = "invalid" if max_severity == 2 else "warning" if max_severity == 1 else "valid"
    metadata = template_metadata(template_key)
    return {
        "key": template_key,
        "name": template.get("name") or template_key,
        "source": "builtin",
        "shared": True,
        **metadata,
        "status": status,
        "nodes_count": len(nodes),
        "transitions_count": len(transitions),
        "block_types": [{"type": key, "count": value} for key, value in sorted(block_types.items())],
        "hidden_blocks": sorted(set(hidden_blocks)),
        "unsupported_blocks": sorted(set(unsupported_blocks)),
        "issues": issues,
    }


class GeneratedFlowApply(BaseModel):
    name: str | None = None
    nodes: list[AiGeneratedNode]
    transitions: list[AiGeneratedTransition]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_chatbot_access(db: Session, chatbot_id: int, current_user: User) -> Chatbot:
    query = db.query(Chatbot).filter(Chatbot.id == chatbot_id)
    if current_user.role == "manager":
        query = query.join(Project, Chatbot.project_id == Project.id).filter(Project.user_id == current_user.id)

    chatbot = query.first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")
    return chatbot


def ensure_version_access(db: Session, version_id: int, current_user: User) -> VersionChatbot:
    version = db.query(VersionChatbot).filter(VersionChatbot.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    ensure_chatbot_access(db, version.chatbot_id, current_user)
    return version


def ensure_flow_access(db: Session, flow_id: int, current_user: User) -> Flow:
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    ensure_version_access(db, flow.version_id, current_user)
    return flow


def ensure_node_access(db: Session, node_id: int, current_user: User) -> FlowNode:
    node = db.query(FlowNode).filter(FlowNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    ensure_flow_access(db, node.flow_id, current_user)
    return node


def ensure_transition_access(db: Session, transition_id: int, current_user: User) -> FlowTransition:
    transition = db.query(FlowTransition).filter(FlowTransition.id == transition_id).first()
    if not transition:
        raise HTTPException(status_code=404, detail="Transition not found")
    ensure_flow_access(db, transition.flow_id, current_user)
    return transition


def _can_read_custom_template(template: FlowTemplate, current_user: User) -> bool:
    return current_user.role == "admin" or template.owner_id == current_user.id or bool(template.is_shared)


def _can_manage_custom_template(template: FlowTemplate, current_user: User) -> bool:
    return current_user.role == "admin" or template.owner_id == current_user.id


def _custom_template_query(db: Session, current_user: User):
    query = db.query(FlowTemplate)
    if current_user.role == "manager":
        query = query.filter((FlowTemplate.owner_id == current_user.id) | (FlowTemplate.is_shared == True))  # noqa: E712
    return query


def _custom_template_payload(template: FlowTemplate) -> dict:
    return {
        "key": template.key,
        "name": template.name,
        "description": template.description or "",
        "purposes": [template.purpose or "custom"],
        "primary_purpose": template.purpose or "custom",
        "exposed": bool(template.is_exposed),
        "shared": bool(template.is_shared),
        "owner_id": template.owner_id,
        "source": "custom",
        "current_revision_number": template.current_revision_number or 1,
        "nodes": template.nodes or [],
        "transitions": template.transitions or [],
        "test_scenarios": template.test_scenarios or [],
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def _template_ownership_scope(template: FlowTemplate, current_user: User) -> str:
    if template.owner_id == current_user.id:
        return "mine"
    return "shared"


def _revision_payload(revision: FlowTemplateRevision) -> dict:
    return {
        "id": revision.id,
        "revision_number": revision.revision_number,
        "name": revision.name,
        "description": revision.description or "",
        "purpose": revision.purpose or "custom",
        "nodes_count": len(revision.nodes or []),
        "transitions_count": len(revision.transitions or []),
        "test_scenarios_count": len(revision.test_scenarios or []),
        "change_note": revision.change_note or "",
        "created_by": revision.created_by,
        "created_at": revision.created_at,
    }


def _latest_template_revision(db: Session, template: FlowTemplate) -> FlowTemplateRevision | None:
    return db.query(FlowTemplateRevision).filter(
        FlowTemplateRevision.template_id == template.id
    ).order_by(FlowTemplateRevision.revision_number.desc()).first()


def _template_revision(db: Session, template: FlowTemplate, revision_number: int | None = None) -> FlowTemplateRevision | None:
    query = db.query(FlowTemplateRevision).filter(FlowTemplateRevision.template_id == template.id)
    if revision_number is not None:
        return query.filter(FlowTemplateRevision.revision_number == revision_number).first()
    return query.order_by(FlowTemplateRevision.revision_number.desc()).first()


def _create_template_revision(
    db: Session,
    template: FlowTemplate,
    current_user: User,
    nodes: list[dict],
    transitions: list[dict],
    test_scenarios: list[dict] | None = None,
    change_note: str | None = None,
) -> FlowTemplateRevision:
    latest = _latest_template_revision(db, template)
    revision_number = (latest.revision_number if latest else 0) + 1
    revision = FlowTemplateRevision(
        template_id=template.id,
        revision_number=revision_number,
        name=template.name,
        description=template.description or "",
        purpose=template.purpose or "custom",
        nodes=nodes,
        transitions=transitions,
        test_scenarios=test_scenarios if test_scenarios is not None else (template.test_scenarios or []),
        change_note=(change_note or "").strip()[:600],
        created_by=current_user.id,
    )
    db.add(revision)
    template.current_revision_number = revision_number
    template.nodes = nodes
    template.transitions = transitions
    if test_scenarios is not None:
        template.test_scenarios = test_scenarios
    return revision


def _template_from_db(db: Session, template_key: str, current_user: User) -> FlowTemplate | None:
    template = db.query(FlowTemplate).filter(FlowTemplate.key == template_key).first()
    if template and not _can_read_custom_template(template, current_user):
        raise HTTPException(status_code=404, detail="Template not found")
    return template


def _analyze_payload_template(payload: dict) -> dict:
    nodes = [
        (
            node.get("key"),
            node.get("type"),
            node.get("label"),
            node.get("config") or {},
            node.get("position_x", 0),
            node.get("position_y", 0),
        )
        for node in payload.get("nodes", [])
    ]
    transitions = [
        (
            transition.get("source_node_key"),
            transition.get("target_node_key"),
            transition.get("label"),
            transition.get("condition"),
        )
        for transition in payload.get("transitions", [])
    ]
    analysis = analyze_template_quality(payload.get("key") or "", {
        "name": payload.get("name"),
        "nodes": nodes,
        "transitions": transitions,
    })
    analysis.update({
        "description": payload.get("description") or "",
        "purposes": payload.get("purposes") or [],
        "primary_purpose": payload.get("primary_purpose") or "custom",
        "exposed": bool(payload.get("exposed")),
        "shared": bool(payload.get("shared")),
        "owner_id": payload.get("owner_id"),
        "source": payload.get("source") or "custom",
        "current_revision_number": payload.get("current_revision_number") or payload.get("selected_revision_number") or 1,
        "selected_revision_number": payload.get("selected_revision_number") or payload.get("current_revision_number") or 1,
        "nodes": payload.get("nodes") or [],
        "transitions": payload.get("transitions") or [],
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    })
    return analysis


def _current_flow_payload(flow: Flow) -> tuple[list[dict], list[dict]]:
    nodes = [
        {
            "key": node.node_key,
            "type": node.type,
            "label": node.label,
            "config": node.config or {},
            "position_x": node.position_x,
            "position_y": node.position_y,
        }
        for node in sorted(flow.nodes, key=lambda item: (item.position_y or 0, item.position_x or 0, item.id or 0))
    ]
    transitions = [
        {
            "source_node_key": transition.source_node_key,
            "target_node_key": transition.target_node_key,
            "label": transition.label,
            "condition": transition.condition,
        }
        for transition in sorted(flow.transitions, key=lambda item: item.id or 0)
    ]
    return nodes, transitions


def _runtime_graph_from_payload(nodes: list[dict], transitions: list[dict]) -> tuple[Flow, list[FlowNode], list[FlowTransition]]:
    flow = Flow(id=0, version_id=0, name="Template Test")
    runtime_nodes = [
        FlowNode(
            id=index + 1,
            flow_id=0,
            node_key=_item_value(node, "key"),
            type=_item_value(node, "type"),
            label=_item_value(node, "label"),
            config=node.get("config") or {},
            position_x=_item_value(node, "position_x") or 0,
            position_y=_item_value(node, "position_y") or 0,
        )
        for index, node in enumerate(nodes or [])
    ]
    runtime_transitions = [
        FlowTransition(
            id=index + 1,
            flow_id=0,
            source_node_key=_item_value(transition, "source_node_key"),
            target_node_key=_item_value(transition, "target_node_key"),
            label=transition.get("label"),
            condition=transition.get("condition"),
        )
        for index, transition in enumerate(transitions or [])
    ]
    return flow, runtime_nodes, runtime_transitions


def _test_rag_answer(query: str, variables: dict, config: dict | None = None) -> dict:
    response = (config or {}).get("test_response") or f"Test AI answer for: {query or 'empty input'}"
    return {
        "response": response,
        "messages": [{"text": response, "options": []}],
        "mode_used": "template_test_rag",
        "sources": [],
        "variables": variables,
    }


def _default_message_for_node(node: FlowNode, transitions: list[FlowTransition]) -> str:
    config = node.config or {}
    if node.type == "collect_email":
        return "test@example.com"
    if node.type == "collect_phone":
        return "+21612345678"
    if node.type == "collect_name":
        return "Test User"
    if node.type == "meeting_scheduler":
        return "Tomorrow at 10:00"
    if node.type == "buttons":
        options = config.get("buttons") or [
            transition.label
            for transition in transitions
            if transition.source_node_key == node.node_key and transition.label
        ]
        return str(options[0]) if options else ""
    if node.type == "question":
        field = str(config.get("field") or node.node_key).lower()
        if "email" in field:
            return "test@example.com"
        if "phone" in field:
            return "+21612345678"
        if "budget" in field:
            return "1500"
        return "Test question"
    if node.type in {"rag_answer", "knowledge_search"}:
        return "Test question"
    return ""


def _run_template_scenario(template: dict, scenario: FlowTemplateTestRun) -> dict:
    nodes = template.get("nodes") or []
    transitions = template.get("transitions") or []
    runtime_graph = _runtime_graph_from_payload(nodes, transitions)
    node_by_key = {node.node_key: node for node in runtime_graph[1]}
    variables = {"__language": "en"}
    current_node_key = None
    transcript: list[dict] = []
    path: list[str] = []
    errors: list[str] = []

    def record(message: str, result: dict):
        response = result.get("response") or ""
        transcript.append({
            "input": message,
            "response": response,
            "messages": result.get("messages") or [],
            "current_node_key": result.get("current_node_key"),
            "mode_used": result.get("mode_used"),
        })
        if result.get("current_node_key"):
            path.append(result["current_node_key"])

    try:
        result = execute_flow(
            db=None,
            version_id=0,
            message="",
            current_node_key=None,
            variables=variables,
            rag_answer=_test_rag_answer,
            allow_rag_fallback=True,
            _runtime_graph=runtime_graph,
        )
        variables = result.get("variables") or variables
        current_node_key = result.get("current_node_key")
        record("__start__", result)

        messages = scenario.messages
        if messages is None:
            messages = []
            for _ in range(12):
                current_node = node_by_key.get(current_node_key or "")
                if not current_node:
                    break
                message = _default_message_for_node(current_node, runtime_graph[2])
                if not message:
                    break
                messages.append(message)
                probe = execute_flow(
                    db=None,
                    version_id=0,
                    message=message,
                    current_node_key=current_node_key,
                    variables=variables,
                    rag_answer=_test_rag_answer,
                    allow_rag_fallback=True,
                    _runtime_graph=runtime_graph,
                )
                variables = probe.get("variables") or variables
                current_node_key = probe.get("current_node_key")
                record(message, probe)
                if probe.get("runtime_error") or not current_node_key:
                    break
            return _template_test_result(scenario, transcript, path, variables, current_node_key, errors)

        for message in messages:
            result = execute_flow(
                db=None,
                version_id=0,
                message=message,
                current_node_key=current_node_key,
                variables=variables,
                rag_answer=_test_rag_answer,
                allow_rag_fallback=True,
                _runtime_graph=runtime_graph,
            )
            variables = result.get("variables") or variables
            current_node_key = result.get("current_node_key")
            record(message, result)
            if result.get("runtime_error"):
                errors.append(result["runtime_error"].get("message") or "Runtime error")
                break
    except Exception as exc:
        errors.append(str(exc))

    return _template_test_result(scenario, transcript, path, variables, current_node_key, errors)


def _template_test_result(
    scenario: FlowTemplateTestRun,
    transcript: list[dict],
    path: list[str],
    variables: dict,
    current_node_key: str | None,
    errors: list[str],
) -> dict:
    expected_variables = scenario.expected_variables or {}
    for key, expected in expected_variables.items():
        if variables.get(key) != expected:
            errors.append(f"Expected variable '{key}' to equal '{expected}', got '{variables.get(key)}'.")
    if scenario.expected_final_node_key is not None and current_node_key != scenario.expected_final_node_key:
        errors.append(f"Expected final node '{scenario.expected_final_node_key}', got '{current_node_key or 'completed'}'.")
    return {
        "name": scenario.name or "Ad hoc test",
        "status": "failed" if errors else "passed",
        "errors": errors,
        "path": path,
        "final_node_key": current_node_key,
        "variables": variables,
        "transcript": transcript,
    }


def _compact(value: str | None, fallback: str = "") -> str:
    return " ".join((value or fallback).strip().split())


def _json_object_from_text(value: str) -> dict:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,;\n]", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []
    clean = [_compact(str(item)) for item in items if _compact(str(item))]
    return clean or ["general assistance"]


def _has_any(text: str, terms: set[str]) -> bool:
    for term in terms:
        clean = term.strip().lower()
        if not clean:
            continue
        if " " in clean or "-" in clean:
            if clean in text:
                return True
            continue
        if re.search(rf"\b{re.escape(clean)}\b", text):
            return True
    return False


def _extract_safe_http_url(*values: str) -> str:
    text = " ".join(value or "" for value in values)
    match = re.search(r"https?://[^\s\"'<>),]+", text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;")


def _ensure_canvas_position(position_x: int, position_y: int) -> None:
    if not is_valid_canvas_position(position_x) or not is_valid_canvas_position(position_y):
        raise HTTPException(status_code=400, detail="Node position is outside the supported canvas bounds")


def _item_value(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key)


def _ensure_flow_size(nodes_count: int, transitions_count: int) -> None:
    if nodes_count > MAX_FLOW_NODES:
        raise HTTPException(status_code=400, detail=f"Flow cannot exceed {MAX_FLOW_NODES} nodes")
    if transitions_count > MAX_FLOW_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"Flow cannot exceed {MAX_FLOW_TRANSITIONS} transitions")


def _ensure_transition_nodes_exist(db: Session, flow_id: int, source_key: str, target_key: str) -> None:
    source = db.query(FlowNode).filter(
        FlowNode.flow_id == flow_id,
        FlowNode.node_key == source_key
    ).first()
    target = db.query(FlowNode).filter(
        FlowNode.flow_id == flow_id,
        FlowNode.node_key == target_key
    ).first()
    if not source or not target:
        raise HTTPException(status_code=400, detail="Source and target nodes must exist")


def _ensure_unique_transition(
    db: Session,
    flow_id: int,
    source_key: str,
    target_key: str,
    label: str | None,
    condition: str | None,
    transition_id: int | None = None,
) -> None:
    output_key = normalize_transition_output_key(label, condition)
    transitions = db.query(FlowTransition).filter(FlowTransition.flow_id == flow_id).all()
    for transition in transitions:
        if transition_id is not None and transition.id == transition_id:
            continue
        if (
            transition.source_node_key == source_key
            and transition.target_node_key == target_key
            and normalize_transition_output_key(transition.label, transition.condition) == output_key
        ):
            raise HTTPException(
                status_code=400,
                detail="Duplicate transition with the same source, target, and output key",
            )


def _ensure_generated_transition_uniqueness(transitions: list) -> None:
    seen: set[tuple[str, str, str]] = set()
    for transition in transitions:
        key = (
            _item_value(transition, "source_node_key"),
            _item_value(transition, "target_node_key"),
            normalize_transition_output_key(_item_value(transition, "label"), _item_value(transition, "condition")),
        )
        if key in seen:
            raise HTTPException(
                status_code=400,
                detail="Duplicate transition with the same source, target, and output key",
            )
        seen.add(key)


def _analyze_generation_context(goal: str, context: str, knowledge: str) -> dict:
    text = f"{goal} {context} {knowledge}".lower()
    api_url = _extract_safe_http_url(goal, context, knowledge)
    domain_terms = {
        "education": {"education", "school", "university", "student", "course", "training", "certification", "learning"},
        "healthcare": {"health", "clinic", "patient", "doctor", "medical", "appointment", "care"},
        "banking": {"bank", "loan", "credit", "account", "payment", "finance", "insurance"},
        "e-commerce": {"shop", "store", "order", "product", "cart", "delivery", "refund", "ecommerce", "e-commerce"},
        "HR": {"employee", "hr", "policy", "onboarding", "leave", "benefits", "internal"},
        "IT helpdesk": {"it", "helpdesk", "technical", "device", "password", "microsoft", "cloud", "azure", "security"},
        "sales": {"lead", "sales", "prospect", "quote", "consultation", "qualify", "customer"},
        "legal": {"legal", "contract", "law", "compliance", "case"},
        "real estate": {"real estate", "property", "rent", "buyer", "listing"},
        "tourism": {"tourism", "travel", "hotel", "booking", "trip", "tour"},
    }
    detected_domain = "custom business"
    for domain, terms in domain_terms.items():
        if _has_any(text, terms):
            detected_domain = domain
            break

    needs_rag = bool(knowledge) or _has_any(text, {"document", "knowledge base", "policy", "manual", "faq", "catalog", "documentation", "uploaded"})
    needs_lead = _has_any(text, {"lead", "sales", "prospect", "qualify", "capture", "contact", "quote", "consultation"})
    needs_handoff = _has_any(text, {"handoff", "human", "agent", "escalate", "complex", "support team", "advisor"})
    needs_routing = _has_any(text, {"multiple", "topics", "route", "routing", "department", "category", "intent"})
    needs_booking = _has_any(text, {"appointment", "booking", "schedule", "meeting", "reservation", "consultation"})
    needs_api = False
    suggests_api = False
    needs_condition = needs_lead or _has_any(text, {"if", "score", "eligibility", "qualify", "decision"})

    intents = ["answer questions"]
    if needs_routing:
        intents.append("route users by intent")
    if needs_lead:
        intents.append("capture and qualify leads")
    if needs_booking:
        intents.append("capture meeting preferences")
    if needs_handoff:
        intents.append("escalate to a human")

    variables = ["user_question"]
    if needs_lead or needs_handoff or needs_booking:
        variables.extend(["user_name", "user_email"])
    if needs_lead or needs_booking:
        variables.append("user_phone")
    if needs_routing:
        variables.append("detected_intent")
    if needs_condition:
        variables.append("lead_score")
    if needs_booking:
        variables.append("preferred_time")

    blocks = []
    if needs_routing:
        blocks.extend(["AI Router", "AI Classifier"])
    if needs_rag:
        blocks.append("Knowledge Search")
    if needs_condition:
        blocks.extend(["Confidence Check", "Lead Score"])
    if needs_booking:
        blocks.append("Meeting Preference")
    if needs_handoff:
        blocks.append("Human Handoff")

    flow_type = "simple_ai_chat"
    if needs_lead:
        flow_type = "lead_qualification"
    elif needs_booking:
        flow_type = "booking_assistant"
    elif needs_routing:
        flow_type = "intent_routing_assistant"
    elif needs_rag:
        flow_type = "knowledge_assistant"

    confidence = 0.62
    confidence += 0.1 if detected_domain != "custom business" else 0
    confidence += 0.08 if needs_rag else 0
    confidence += 0.05 if len(intents) > 1 else 0

    return {
        "domain_label": detected_domain,
        "domain_title": detected_domain.title().replace("-", " "),
        "detected_domain": detected_domain,
        "detected_intents": intents,
        "recommended_flow_type": flow_type,
        "needs_rag": needs_rag,
        "needs_lead": needs_lead,
        "needs_handoff": needs_handoff,
        "needs_routing": needs_routing,
        "needs_booking": needs_booking,
        "needs_api": needs_api,
        "suggests_api": suggests_api,
        "api_url": api_url,
        "needs_condition": needs_condition,
        "suggested_variables": list(dict.fromkeys(variables)),
        "suggested_kb_categories": [
            f"{detected_domain} FAQs",
            "Policies and procedures",
            "Product or service documentation",
            "Escalation guidelines",
        ] if needs_rag else [],
        "suggested_advanced_blocks": list(dict.fromkeys(blocks)),
        "generation_confidence": min(confidence, 0.92),
        "generation_explanation": (
            f"Generated a {flow_type.replace('_', ' ')} because the goal/context indicate "
            f"{', '.join(intents)} for the {detected_domain} domain."
        ),
        "use_knowledge_base": needs_rag,
    }


def _node(key: str, node_type: str, label: str, config: dict, x: int, y: int) -> dict:
    return {
        "key": key,
        "type": node_type,
        "label": label,
        "config": config,
        "position_x": x,
        "position_y": y,
    }


def _edge(source: str, target: str, label: str = "next", condition: str | None = None) -> dict:
    return {
        "source_node_key": source,
        "target_node_key": target,
        "label": label,
        "condition": condition,
    }


def _localized_ai_text(language: str, english: str, french: str) -> str:
    return french if language == "fr" else english


def _build_generated_flow(welcome_message: str, rag_prompt: str, analysis: dict, language: str = "en") -> tuple[list[dict], list[dict]]:
    needs_rag = bool(analysis.get("needs_rag"))
    nodes = [_node("start", "message", "Welcome", {"text": welcome_message}, 80, 120)]
    edges = []
    previous = "start"
    x = 340

    def add(key: str, node_type: str, label: str, config: dict):
        nonlocal previous, x
        nodes.append(_node(key, node_type, label, config, x, 120))
        edges.append(_edge(previous, key))
        previous = key
        x += 260

    if analysis.get("needs_routing"):
        add("router", "ai_router", "AI Router", {
            "instructions": _localized_ai_text(language, "Classify the user's intent and route the conversation to the best next step.", "Classez l'intention de l'utilisateur et orientez la conversation vers la meilleure prochaine etape."),
            "output_variable": "detected_intent",
            "routes": analysis.get("detected_intents", []),
            "message": _localized_ai_text(language, "Let me route your request.", "Je vais orienter votre demande.")
        })

    if analysis.get("needs_lead") or analysis.get("needs_booking") or analysis.get("needs_handoff"):
        add("collect_name", "collect_name", "Collect Name", {"prompt": _localized_ai_text(language, "What is your name?", "Quel est votre nom ?"), "field": "user_name"})
        add("collect_email", "collect_email", "Collect Email", {"prompt": _localized_ai_text(language, "What email should we use?", "Quel email devons-nous utiliser ?"), "field": "user_email"})

    if analysis.get("needs_lead") or analysis.get("needs_booking"):
        add("collect_phone", "collect_phone", "Collect Phone", {"prompt": _localized_ai_text(language, "What phone number can we use?", "Quel numero de telephone pouvons-nous utiliser ?"), "field": "user_phone"})

    if analysis.get("needs_condition"):
        add("lead_score", "lead_score", "Lead Score", {
            "input_variables": ["user_question", "user_email"],
            "score_variable": "lead_score",
            "message": _localized_ai_text(language, "I am qualifying this request.", "J'evalue cette demande.")
        })
        add("confidence", "confidence_check", "Confidence Check", {
            "threshold": 0.65,
            "variable": "lead_score",
            "message": "Checking confidence."
        })

    if analysis.get("needs_booking"):
        add("scheduler", "meeting_scheduler", "Meeting Preference", {
            "field": "preferred_time",
            "prompt": _localized_ai_text(language, "Share your preferred meeting time.", "Indiquez votre disponibilite preferee."),
            "timezone": "local",
            "success_message": _localized_ai_text(language, "Meeting preference saved.", "Preference de rendez-vous enregistree.")
        })

    add("question", "question", "User Question", {
        "prompt": _localized_ai_text(language, "Ask me anything.", "Posez-moi votre question."),
        "field": "user_question",
        "silent": True,
        "hide_prompt": True
    })

    if needs_rag:
        add("knowledge_search", "knowledge_search", "Knowledge Search", {
            "prompt": _localized_ai_text(language, "Retrieve relevant knowledge base context for the user's question.", "Recuperez le contexte pertinent de la base de connaissances pour la question de l'utilisateur."),
            "fallback": _localized_ai_text(language, "I could not find enough relevant knowledge.", "Je n'ai pas trouve assez d'informations pertinentes."),
            "use_knowledge_base": True,
            "show_sources": True,
            "continue_rag": False,
            "retrieval_only": True,
            "message": _localized_ai_text(language, "Searching knowledge.", "Recherche dans les connaissances.")
        })

    add("answer", "rag_answer", "AI Answer", {
        "prompt": rag_prompt,
        "fallback": _localized_ai_text(language, "I do not have enough information to answer that yet.", "Je n'ai pas encore assez d'informations pour repondre."),
        "use_knowledge_base": needs_rag,
        "show_sources": needs_rag,
        "continue_rag": False,
        "message": _localized_ai_text(language, "Searching knowledge and preparing an answer.", "Recherche dans les connaissances et preparation d'une reponse.") if needs_rag else _localized_ai_text(language, "Preparing an answer.", "Preparation d'une reponse.")
    })

    edges.append(_edge("answer", "question"))

    if analysis.get("needs_handoff"):
        nodes.append(_node("handoff", "handoff", "Human Handoff", {
            "message": "A teammate will review this request and follow up.",
            "department": "Support",
            "email_field": "user_email",
            "phone_field": "user_phone",
            "collect_email_if_missing": True
        }, x, 300))
        edges.append(_edge("answer", "handoff", "fallback", "low_confidence_or_human_requested"))

    return nodes, edges


def _fallback_ai_generation(payload: AiGenerateRequest) -> dict:
    language = safe_chatbot_language(payload.language)
    goal = _compact(payload.assistant_goal, "Help users get accurate answers")
    context = _compact(payload.business_context, "the organization")
    knowledge = _compact(payload.knowledge_base_description)
    analysis = _analyze_generation_context(goal, context, knowledge)
    assistant_name = f"{analysis['domain_title']} Assistant"

    return {
        "assistant_name": assistant_name,
        "assistant_description": _localized_ai_text(
            language,
            f"Assistant designed to {goal.lower()} for {context}.",
            f"Assistant concu pour {goal.lower()} pour {context}."
        ),
        "welcome_message": _localized_ai_text(
            language,
            f"Hi. I can help with {analysis['domain_label']} questions and requests. How can I help?",
            f"Bonjour. Je peux vous aider avec les questions et demandes liees a {analysis['domain_label']}. Comment puis-je vous aider ?"
        ),
        "recommended_template": analysis["recommended_flow_type"],
        "rag_prompt": (
            ("Always answer in French. " if language == "fr" else "")
            + f"Use the available knowledge base to answer questions about {context}. "
            f"Assistant goal: {goal}. Be clear, professional, and practical."
        ) if analysis["needs_rag"] else (
            ("Always answer in French. " if language == "fr" else "")
            + f"Answer questions for {context}. Assistant goal: {goal}. "
            "Be clear, professional, and practical."
        ),
        "use_knowledge_base": analysis["needs_rag"],
        **analysis,
    }


def _normalize_ai_generation(raw: dict, payload: AiGenerateRequest) -> AiGenerateResponse:
    fallback = _fallback_ai_generation(payload)
    language = safe_chatbot_language(payload.language)
    assistant_name = _compact(raw.get("assistant_name"), fallback["assistant_name"])[:120]
    assistant_description = _compact(raw.get("assistant_description"), fallback["assistant_description"])[:500]
    welcome_message = _compact(raw.get("welcome_message"), fallback["welcome_message"])[:300]
    recommended_template = _compact(raw.get("recommended_template"), fallback["recommended_template"])[:80]
    rag_prompt = _compact(raw.get("rag_prompt"), fallback["rag_prompt"])[:700]
    analysis = {**fallback, **raw}
    api_url = _extract_safe_http_url(
        _compact(raw.get("api_url")),
        payload.assistant_goal,
        payload.business_context,
        payload.knowledge_base_description or "",
    )
    analysis["api_url"] = api_url
    analysis["needs_api"] = False
    analysis["suggests_api"] = False
    use_knowledge_base = bool(analysis.get("use_knowledge_base", fallback["use_knowledge_base"]))
    analysis["needs_rag"] = use_knowledge_base
    if language == "fr" and "Always answer in French." not in rag_prompt:
        rag_prompt = f"Always answer in French. {rag_prompt}"
    nodes, transitions = _build_generated_flow(welcome_message, rag_prompt, analysis, language)
    detected_domain = _string_list(analysis.get("detected_domain") or analysis.get("domain_label") or fallback["domain_label"])[0]
    detected_intents = _string_list(analysis.get("detected_intents") or fallback["detected_intents"])
    suggested_variables = _string_list(analysis.get("suggested_variables") or fallback["suggested_variables"])
    suggested_kb_categories = _string_list(analysis.get("suggested_kb_categories") or fallback["suggested_kb_categories"])
    suggested_advanced_blocks = [
        block for block in _string_list(analysis.get("suggested_advanced_blocks") or fallback["suggested_advanced_blocks"])
        if block != "API Call"
    ]
    generation_confidence = max(0.1, min(float(analysis.get("generation_confidence") or fallback["generation_confidence"]), 0.98))
    explanation = _compact(analysis.get("generation_explanation"), fallback["generation_explanation"])[:800]

    return AiGenerateResponse(
        assistant_name=assistant_name,
        assistant_description=assistant_description,
        welcome_message=welcome_message,
        recommended_template=recommended_template,
        detected_domain=detected_domain,
        detected_intents=detected_intents,
        recommended_flow_type=_compact(analysis.get("recommended_flow_type"), fallback["recommended_flow_type"])[:80],
        generated_nodes=nodes,
        generated_edges=transitions,
        suggested_variables=suggested_variables,
        suggested_kb_categories=suggested_kb_categories,
        suggested_advanced_blocks=suggested_advanced_blocks,
        generation_confidence=generation_confidence,
        generation_explanation=explanation,
        initial_flow_structure={
            "nodes": nodes,
            "transitions": transitions,
        },
    )


@router.post("/assistants/ai-generate", response_model=AiGenerateResponse)
def generate_assistant_with_ai(
    payload: AiGenerateRequest,
    current_user=Depends(require_roles("admin", "manager"))
):
    goal = _compact(payload.assistant_goal)
    context = _compact(payload.business_context)
    knowledge = _compact(payload.knowledge_base_description)
    if not goal:
        raise HTTPException(status_code=400, detail="Assistant Goal is required")
    if not context:
        raise HTTPException(status_code=400, detail="Business Context is required")

    prompt = f"""
Generate a chatbot assistant plan for an enterprise manager.
Assistant language: {safe_chatbot_language(payload.language)}. Generate all user-facing content in {"French" if safe_chatbot_language(payload.language) == "fr" else "English"}.

Return only valid JSON with these keys:
- assistant_name
- assistant_description
- welcome_message
- recommended_template
- rag_prompt
- use_knowledge_base
- detected_domain
- detected_intents
- recommended_flow_type
- suggested_variables
- suggested_kb_categories
- suggested_advanced_blocks
- generation_confidence
- generation_explanation

Rules:
- assistant_name must be concise.
- assistant_description must explain the assistant's business purpose.
- welcome_message must be generated from the provided goal and business context.
- recommended_template must be a short snake_case label.
- rag_prompt must be instructions for the AI or AI/RAG answer node based on the context.
- use_knowledge_base must be true only when uploaded documents are useful.
- Do not assume any company, industry, or use case that is not provided.
- Infer whether routing, lead capture, handoff, booking, API actions, or conditions are useful.

Assistant goal:
{goal}

Business context:
{context}

Optional knowledge base description:
{knowledge or "None"}

Assistant type:
{payload.assistant_type or "custom"}
"""

    try:
        content = generate_chat_completion(prompt, None, 0.2, 700)
        generated = _json_object_from_text(content)
    except (AIProviderError, json.JSONDecodeError, TypeError, ValueError):
        generated = _fallback_ai_generation(payload)

    return _normalize_ai_generation(generated, payload)


@router.get("/versions/{version_id}/flow", response_model=FlowResponse)
def get_flow(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    version = ensure_version_access(db, version_id, current_user)

    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if not flow:
        chatbot = db.query(Chatbot).filter(Chatbot.id == version.chatbot_id).first()
        flow = create_starter_flow(db, version_id, "blank", chatbot.language if chatbot else None)

    return flow


@router.get("/versions/{version_id}/flow/validate")
def validate_flow(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    ensure_version_access(db, version_id, current_user)

    result = validate_flow_version(db, version_id)
    return result


@router.get("/flow-templates")
def list_flow_templates(
    purpose: str | None = None,
    exposed_only: bool = False,
    include_builtin: bool = True,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    requested_purpose = str(purpose or "").strip()
    items = template_options(purpose=requested_purpose or None, exposed_only=exposed_only) if include_builtin else []
    for template in _custom_template_query(db, current_user).order_by(FlowTemplate.updated_at.desc(), FlowTemplate.id.desc()).all():
        if requested_purpose and requested_purpose != (template.purpose or "custom"):
            continue
        if exposed_only and not template.is_exposed:
            continue
        items.append({
            "key": template.key,
            "name": template.name,
            "description": template.description or "",
            "purposes": [template.purpose or "custom"],
            "primary_purpose": template.purpose or "custom",
            "exposed": bool(template.is_exposed),
            "shared": bool(template.is_shared),
            "owner_id": template.owner_id,
            "ownership_scope": _template_ownership_scope(template, current_user),
            "source": "custom",
            "current_revision_number": template.current_revision_number or 1,
        })
    return items


@router.get("/flow-templates/qa")
def template_quality_report(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    items = []
    for key, template in sorted(TEMPLATES.items()):
        item = analyze_template_quality(key, template)
        item["ownership_scope"] = "builtin"
        items.append(item)
    items.extend(
        {
            **_analyze_payload_template(_custom_template_payload(template)),
            "ownership_scope": _template_ownership_scope(template, current_user),
        }
        for template in _custom_template_query(db, current_user).order_by(FlowTemplate.updated_at.desc(), FlowTemplate.id.desc()).all()
    )
    return {
        "summary": {
            "total": len(items),
            "valid": sum(1 for item in items if item["status"] == "valid"),
            "warning": sum(1 for item in items if item["status"] == "warning"),
            "invalid": sum(1 for item in items if item["status"] == "invalid"),
            "hidden_block_templates": sum(1 for item in items if item["hidden_blocks"]),
            "custom": sum(1 for item in items if item.get("source") == "custom"),
            "mine": sum(1 for item in items if item.get("ownership_scope") == "mine"),
            "shared": sum(1 for item in items if item.get("shared")),
        },
        "items": items,
    }


@router.get("/flow-templates/{template_key}")
def get_flow_template_detail(
    template_key: str,
    revision: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    custom = _template_from_db(db, template_key, current_user)
    if custom:
        payload = _custom_template_payload(custom)
        selected_revision = _template_revision(db, custom, revision)
        if selected_revision:
            payload.update({
                "name": selected_revision.name,
                "description": selected_revision.description or "",
                "purposes": [selected_revision.purpose or "custom"],
                "primary_purpose": selected_revision.purpose or "custom",
                "nodes": selected_revision.nodes or [],
                "transitions": selected_revision.transitions or [],
                "test_scenarios": selected_revision.test_scenarios or [],
                "selected_revision_number": selected_revision.revision_number,
            })
        else:
            payload["selected_revision_number"] = custom.current_revision_number or 1
        detail = _analyze_payload_template(payload)
        detail["can_edit"] = _can_manage_custom_template(custom, current_user)
        detail["ownership_scope"] = _template_ownership_scope(custom, current_user)
        revisions = db.query(FlowTemplateRevision).filter(
            FlowTemplateRevision.template_id == custom.id
        ).order_by(FlowTemplateRevision.revision_number.desc()).all()
        detail["revisions"] = [_revision_payload(item) for item in revisions]
        return detail

    template = TEMPLATES.get(template_key)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    nodes, transitions = template_generated_payload(template_key)
    detail = analyze_template_quality(template_key, template)
    detail.update({
        "source": "builtin",
        "shared": True,
        "ownership_scope": "builtin",
        "can_edit": False,
        "nodes": nodes,
        "transitions": transitions,
        "test_scenarios": [],
        "current_revision_number": 1,
        "selected_revision_number": 1,
        "revisions": [{
            "revision_number": 1,
            "name": detail["name"],
            "description": detail.get("description") or "",
            "purpose": detail.get("primary_purpose") or "internal",
            "nodes_count": len(nodes),
            "transitions_count": len(transitions),
            "test_scenarios_count": 0,
            "change_note": "Built-in template",
            "created_by": None,
            "created_at": None,
        }],
    })
    return detail


@router.patch("/flow-templates/{template_key}")
def update_flow_template(
    template_key: str,
    payload: FlowTemplateUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    template = _template_from_db(db, template_key, current_user)
    if not template:
        if template_key in TEMPLATES:
            raise HTTPException(status_code=400, detail="Built-in templates are read-only")
        raise HTTPException(status_code=404, detail="Template not found")
    if not _can_manage_custom_template(template, current_user):
        raise HTTPException(status_code=403, detail="Only the template owner can update this template")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Template name is required")
        template.name = name[:120]
    if payload.description is not None:
        template.description = payload.description.strip()[:600]
    if payload.purpose is not None:
        template.purpose = payload.purpose.strip() or "custom"
    if payload.is_exposed is not None:
        template.is_exposed = payload.is_exposed
    if payload.is_shared is not None:
        template.is_shared = payload.is_shared
    if payload.test_scenarios is not None:
        template.test_scenarios = payload.test_scenarios[:20]

    db.commit()
    db.refresh(template)
    detail = _analyze_payload_template(_custom_template_payload(template))
    detail["can_edit"] = True
    detail["ownership_scope"] = _template_ownership_scope(template, current_user)
    return detail


@router.post("/flow-templates/{template_key}/test")
def run_flow_template_test(
    template_key: str,
    payload: FlowTemplateTestRun | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    detail = get_flow_template_detail(template_key, db=db, current_user=current_user)
    scenarios = []
    if payload and (payload.messages is not None or payload.expected_variables or payload.expected_final_node_key):
        scenarios = [payload]
    else:
        scenarios = [
            FlowTemplateTestRun(**scenario)
            for scenario in detail.get("test_scenarios") or []
        ]
        if not scenarios:
            scenarios = [FlowTemplateTestRun(name="Auto path smoke test")]

    results = [_run_template_scenario(detail, scenario) for scenario in scenarios]
    status = "failed" if any(result["status"] == "failed" for result in results) else "passed"
    return {
        "template_key": template_key,
        "template_name": detail.get("name"),
        "status": status,
        "scenario_count": len(results),
        "results": results,
    }


@router.get("/flow-templates/{template_key}/revisions")
def list_flow_template_revisions(
    template_key: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    custom = _template_from_db(db, template_key, current_user)
    if not custom:
        if template_key not in TEMPLATES:
            raise HTTPException(status_code=404, detail="Template not found")
        detail = get_flow_template_detail(template_key, db=db, current_user=current_user)
        return detail["revisions"]
    revisions = db.query(FlowTemplateRevision).filter(
        FlowTemplateRevision.template_id == custom.id
    ).order_by(FlowTemplateRevision.revision_number.desc()).all()
    return [_revision_payload(item) for item in revisions]


@router.post("/flows/{flow_id}/template-library")
def create_flow_template_from_flow(
    flow_id: int,
    payload: FlowTemplateCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")
    nodes, transitions = _current_flow_payload(flow)
    version = db.query(VersionChatbot).filter(VersionChatbot.id == flow.version_id).first()
    _ensure_flow_size(len(nodes), len(transitions))
    ensure_generated_flow_is_valid(db, version.chatbot_id if version else 0, nodes, transitions, name)

    template = FlowTemplate(
        name=name[:120],
        description=(payload.description or "").strip()[:600],
        purpose=(payload.purpose or "custom").strip() or "custom",
        is_exposed=payload.is_exposed,
        is_shared=payload.is_shared,
        owner_id=current_user.id,
        source_flow_id=flow.id,
        nodes=nodes,
        transitions=transitions,
    )
    db.add(template)
    db.flush()
    template.key = f"custom_template_{template.id}"
    _create_template_revision(
        db,
        template,
        current_user,
        nodes,
        transitions,
        test_scenarios=template.test_scenarios or [],
        change_note=payload.change_note or "Initial template version",
    )
    db.commit()
    db.refresh(template)
    detail = _analyze_payload_template(_custom_template_payload(template))
    detail["can_edit"] = True
    detail["ownership_scope"] = _template_ownership_scope(template, current_user)
    return detail


@router.post("/flows/{flow_id}/template-library/{template_key}/revisions")
def create_flow_template_revision_from_flow(
    flow_id: int,
    template_key: str,
    payload: FlowTemplateRevisionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)
    template = _template_from_db(db, template_key, current_user)
    if not template:
        if template_key in TEMPLATES:
            raise HTTPException(status_code=400, detail="Built-in templates are read-only")
        raise HTTPException(status_code=404, detail="Template not found")
    if not _can_manage_custom_template(template, current_user):
        raise HTTPException(status_code=403, detail="Only the template owner can version this template")

    nodes, transitions = _current_flow_payload(flow)
    version = db.query(VersionChatbot).filter(VersionChatbot.id == flow.version_id).first()
    _ensure_flow_size(len(nodes), len(transitions))
    ensure_generated_flow_is_valid(db, version.chatbot_id if version else 0, nodes, transitions, template.name)
    revision = _create_template_revision(
        db,
        template,
        current_user,
        nodes,
        transitions,
        test_scenarios=template.test_scenarios or [],
        change_note=payload.change_note,
    )
    db.commit()
    db.refresh(template)
    return {
        "template": get_flow_template_detail(template.key, db=db, current_user=current_user),
        "revision": _revision_payload(revision),
    }


@router.post("/flows/{flow_id}/template", response_model=FlowResponse)
def apply_flow_template(
    flow_id: int,
    payload: FlowTemplateApply,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)
    version = db.query(VersionChatbot).filter(VersionChatbot.id == flow.version_id).first()
    chatbot = db.query(Chatbot).filter(Chatbot.id == version.chatbot_id).first() if version else None
    language = chatbot.language if chatbot else None

    try:
        custom_template = _template_from_db(db, payload.template_key, current_user)
        if custom_template:
            selected_revision = _template_revision(db, custom_template, payload.template_revision)
            if not selected_revision:
                raise ValueError("Template revision not found")
            nodes = selected_revision.nodes or []
            transitions = selected_revision.transitions or []
        else:
            selected_revision = None
            nodes, transitions = template_generated_payload(payload.template_key, language)
        _ensure_flow_size(len(nodes), len(transitions))
        for node in nodes:
            _ensure_canvas_position(_item_value(node, "position_x"), _item_value(node, "position_y"))
        _ensure_generated_transition_uniqueness(transitions)
        ensure_generated_flow_is_valid(
            db,
            version.chatbot_id if version else 0,
            nodes,
            transitions,
            payload.template_key,
        )
        if custom_template:
            db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
            db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
            flow.name = custom_template.name
            db.flush()
            for node in nodes:
                db.add(FlowNode(
                    flow_id=flow.id,
                    node_key=_item_value(node, "key"),
                    type=_item_value(node, "type"),
                    label=_item_value(node, "label"),
                    config=node.get("config") or {},
                    position_x=_item_value(node, "position_x"),
                    position_y=_item_value(node, "position_y"),
                ))
            for transition in transitions:
                db.add(FlowTransition(
                    flow_id=flow.id,
                    source_node_key=_item_value(transition, "source_node_key"),
                    target_node_key=_item_value(transition, "target_node_key"),
                    label=transition.get("label"),
                    condition=transition.get("condition"),
                ))
            db.commit()
            db.refresh(flow)
            saved_flow = flow
        else:
            saved_flow = replace_flow_with_template(db, flow, payload.template_key, language)
        if version:
            if chatbot and chatbot.build_method == "template":
                chatbot.template_key = payload.template_key
                chatbot.source_template_key = payload.template_key
                chatbot.source_template_version = str(selected_revision.revision_number) if selected_revision else "builtin"
                if payload.purpose:
                    chatbot.purpose = payload.purpose
                db.commit()
                db.refresh(saved_flow)
        return saved_flow
    except ValueError as exc:
        logger.warning(
            "Template apply failed for flow_id=%s template_key=%s: %s",
            flow_id,
            payload.template_key,
            exc,
        )
        raise HTTPException(status_code=400, detail="Template could not be applied")


@router.post("/flows/{flow_id}/generated", response_model=FlowResponse)
def apply_generated_flow(
    flow_id: int,
    payload: GeneratedFlowApply,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    flow = ensure_flow_access(db, flow_id, current_user)
    version = db.query(VersionChatbot).filter(VersionChatbot.id == flow.version_id).first()
    _ensure_flow_size(len(payload.nodes), len(payload.transitions))
    for node in payload.nodes:
        _ensure_canvas_position(node.position_x, node.position_y)
    _ensure_generated_transition_uniqueness(payload.transitions)
    try:
        nodes, transitions = ensure_generated_flow_is_valid(
            db,
            version.chatbot_id if version else 0,
            payload.nodes,
            payload.transitions,
            payload.name or "AI Generated Assistant",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).delete()
    db.query(FlowNode).filter(FlowNode.flow_id == flow.id).delete()
    flow.name = payload.name or "AI Generated Assistant"
    db.flush()

    for node in nodes:
        db.add(FlowNode(
            flow_id=flow.id,
            node_key=node.key,
            type=node.type,
            label=node.label,
            config=node.config or {},
            position_x=node.position_x,
            position_y=node.position_y,
        ))

    for transition in transitions:
        db.add(FlowTransition(
            flow_id=flow.id,
            source_node_key=transition.source_node_key,
            target_node_key=transition.target_node_key,
            label=transition.label,
            condition=transition.condition,
        ))

    db.commit()
    db.refresh(flow)
    return flow


@router.get("/chatbots/{chatbot_id}/builder", response_model=BuilderContextResponse)
def get_chatbot_builder(
    chatbot_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager"))
):
    chatbot = ensure_chatbot_access(db, chatbot_id, current_user)

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
        flow = create_starter_flow(db, version.id, "blank", chatbot.language)

    return {
        "chatbot": {
            "id": chatbot.id,
            "name": chatbot.name,
            "description": chatbot.description,
            "language": safe_chatbot_language(chatbot.language),
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
    flow = ensure_flow_access(db, flow_id, current_user)
    node_count = db.query(FlowNode).filter(FlowNode.flow_id == flow.id).count()
    if node_count >= MAX_FLOW_NODES:
        raise HTTPException(status_code=400, detail=f"Flow cannot exceed {MAX_FLOW_NODES} nodes")
    _ensure_canvas_position(payload.position_x, payload.position_y)

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
    node = ensure_node_access(db, node_id, current_user)
    position_x = payload.position_x if payload.position_x is not None else node.position_x
    position_y = payload.position_y if payload.position_y is not None else node.position_y
    _ensure_canvas_position(position_x, position_y)

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
    node = ensure_node_access(db, node_id, current_user)

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
    flow = ensure_flow_access(db, flow_id, current_user)
    transition_count = db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).count()
    if transition_count >= MAX_FLOW_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"Flow cannot exceed {MAX_FLOW_TRANSITIONS} transitions")

    _ensure_transition_nodes_exist(db, flow_id, payload.source_node_key, payload.target_node_key)
    _ensure_unique_transition(
        db,
        flow_id,
        payload.source_node_key,
        payload.target_node_key,
        payload.label,
        payload.condition,
    )

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
    transition = ensure_transition_access(db, transition_id, current_user)
    source_key = payload.source_node_key if payload.source_node_key is not None else transition.source_node_key
    target_key = payload.target_node_key if payload.target_node_key is not None else transition.target_node_key
    label = payload.label if payload.label is not None else transition.label
    condition = payload.condition if payload.condition is not None else transition.condition
    _ensure_transition_nodes_exist(db, transition.flow_id, source_key, target_key)
    _ensure_unique_transition(
        db,
        transition.flow_id,
        source_key,
        target_key,
        label,
        condition,
        transition_id=transition.id,
    )

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
    transition = ensure_transition_access(db, transition_id, current_user)

    db.delete(transition)
    db.commit()

    return {"message": "Transition deleted"}
