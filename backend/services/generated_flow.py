from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition
from models.version import VersionChatbot
from services.flow_validation import validate_flow_version


SUPPORTED_FLOW_NODE_TYPES = {
    "message",
    "question",
    "buttons",
    "end",
    "rag_answer",
    "knowledge_search",
    "ai_router",
    "ai_classifier",
    "collect_name",
    "collect_email",
    "collect_phone",
    "condition",
    "confidence_check",
    "lead_score",
    "set_variable",
    "meeting_scheduler",
    "api_request",
    "handoff",
    "action",
}


@dataclass(frozen=True)
class NormalizedGeneratedNode:
    key: str
    type: str
    label: str
    config: dict
    position_x: int
    position_y: int


@dataclass(frozen=True)
class NormalizedGeneratedTransition:
    source_node_key: str
    target_node_key: str
    label: str | None = None
    condition: str | None = None


def _as_dict(value) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return dict(value)


def _clean_key(value) -> str:
    return str(value or "").strip()


def normalize_generated_flow(nodes, transitions) -> tuple[list[NormalizedGeneratedNode], list[NormalizedGeneratedTransition]]:
    normalized_nodes: list[NormalizedGeneratedNode] = []
    seen_keys: set[str] = set()
    start_count = 0

    for index, raw_node in enumerate(nodes or []):
        node = _as_dict(raw_node)
        key = _clean_key(node.get("key") or node.get("node_key") or node.get("id"))
        node_type = _clean_key(node.get("type"))
        if not key:
            raise ValueError("Generated node is missing a key")
        if key in seen_keys:
            raise ValueError("Generated node keys must be unique")
        if node_type not in SUPPORTED_FLOW_NODE_TYPES:
            raise ValueError(f"Generated node '{key}' uses unsupported type '{node_type}'")
        if key == "start":
            start_count += 1

        seen_keys.add(key)
        normalized_nodes.append(NormalizedGeneratedNode(
            key=key,
            type=node_type,
            label=_clean_key(node.get("label")) or key.replace("_", " ").title(),
            config=node.get("config") if isinstance(node.get("config"), dict) else {},
            position_x=int(node.get("position_x") if node.get("position_x") is not None else 80 + index * 260),
            position_y=int(node.get("position_y") if node.get("position_y") is not None else 120),
        ))

    if start_count != 1:
        raise ValueError("Generated flow must include exactly one canonical start node with key 'start'")

    normalized_transitions: list[NormalizedGeneratedTransition] = []
    for raw_transition in transitions or []:
        transition = _as_dict(raw_transition)
        source = _clean_key(
            transition.get("source_node_key")
            or transition.get("source")
            or transition.get("source_key")
            or transition.get("from")
        )
        target = _clean_key(
            transition.get("target_node_key")
            or transition.get("target")
            or transition.get("target_key")
            or transition.get("to")
        )
        if source not in seen_keys or target not in seen_keys:
            raise ValueError("Generated transitions must reference generated nodes")
        normalized_transitions.append(NormalizedGeneratedTransition(
            source_node_key=source,
            target_node_key=target,
            label=transition.get("label"),
            condition=transition.get("condition"),
        ))

    return normalized_nodes, normalized_transitions


def validate_generated_flow_candidate(
    db: Session,
    chatbot_id: int,
    nodes: list[NormalizedGeneratedNode],
    transitions: list[NormalizedGeneratedTransition],
    flow_name: str = "Generated Flow",
) -> dict:
    savepoint = db.begin_nested()
    try:
        version = VersionChatbot(chatbot_id=chatbot_id, version_number=0, status="draft")
        db.add(version)
        db.flush()
        flow = Flow(version_id=version.id, name=flow_name)
        db.add(flow)
        db.flush()

        for node in nodes:
            db.add(FlowNode(
                flow_id=flow.id,
                node_key=node.key,
                type=node.type,
                label=node.label,
                config=node.config,
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

        db.flush()
        return validate_flow_version(db, version.id)
    finally:
        savepoint.rollback()


def ensure_generated_flow_is_valid(db: Session, chatbot_id: int, nodes, transitions, flow_name: str = "Generated Flow"):
    normalized_nodes, normalized_transitions = normalize_generated_flow(nodes, transitions)
    validation = validate_generated_flow_candidate(db, chatbot_id, normalized_nodes, normalized_transitions, flow_name)
    if not validation.get("valid"):
        errors = validation.get("errors") or ["Generated flow is structurally invalid."]
        raise ValueError(f"Generated flow is invalid: {' '.join(errors[:3])}")
    return normalized_nodes, normalized_transitions
