from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition
from services.flow_limits import (
    MAX_FLOW_NODES,
    MAX_FLOW_TRANSITIONS,
    is_valid_canvas_position,
    is_valid_http_url,
    normalize_transition_output_key,
)


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def _node_name(node: FlowNode) -> str:
    return node.label or node.node_key


def _has_continue_rag(node: FlowNode) -> bool:
    config = node.config or {}
    return bool(
        config.get("continue_rag")
        or config.get("continue_answering")
        or config.get("continue_ai_rag")
    )


def _has_next(outgoing: dict[str, list[FlowTransition]], node: FlowNode) -> bool:
    return bool(outgoing.get(node.node_key))


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized(str(value)) in {"1", "true", "yes", "on"}


def _is_silent_input(node: FlowNode) -> bool:
    config = node.config or {}
    return any(
        _truthy(config.get(key))
        for key in ("silent", "silent_input", "hide_prompt", "hide_message")
    )


def _is_user_input_node(node: FlowNode) -> bool:
    return node.type in {"question", "buttons", "collect_name", "collect_email", "collect_phone", "meeting_scheduler"}


def _string_items(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _valid_timeout(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return False
    return 0 < timeout <= 30


def _error(
    code: str,
    message: str,
    suggested_fix: str,
    *,
    severity: str = "error",
    node: FlowNode | None = None,
    transition: FlowTransition | None = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "node_id": node.id if node else None,
        "transition_id": transition.id if transition else None,
        "message": message,
        "suggested_fix": suggested_fix,
    }


def _dedupe_errors(errors: list[dict]) -> list[dict]:
    unique: dict[tuple, dict] = {}
    for item in errors:
        key = (
            item["code"],
            item.get("node_id"),
            item.get("transition_id"),
            item["message"],
        )
        unique.setdefault(key, item)
    return list(unique.values())


ADVANCED_PLACEHOLDER_TYPES = {
    "ai_router",
    "ai_classifier",
    "knowledge_search",
    "confidence_check",
    "lead_score",
}


def _add_cycle_errors(
    errors: list[dict],
    nodes: list[FlowNode],
    outgoing: dict[str, list[FlowTransition]],
) -> None:
    node_by_key = {node.node_key: node for node in nodes}
    visited: set[str] = set()
    stack: list[str] = []
    stack_set: set[str] = set()
    reported: set[tuple[str, ...]] = set()

    def visit(key: str) -> None:
        visited.add(key)
        stack.append(key)
        stack_set.add(key)
        for transition in outgoing.get(key, []):
            target = transition.target_node_key
            if target not in node_by_key:
                continue
            if target not in visited:
                visit(target)
                continue
            if target not in stack_set:
                continue

            start_index = stack.index(target)
            cycle_keys = stack[start_index:]
            fingerprint = tuple(sorted(cycle_keys))
            if fingerprint in reported:
                continue
            reported.add(fingerprint)

            cycle_nodes = [node_by_key[item] for item in cycle_keys]
            if any(_is_user_input_node(node) for node in cycle_nodes):
                continue
            node = cycle_nodes[0]
            errors.append(_error(
                "SILENT_MACHINE_CYCLE",
                f"Machine-only cycle detected around '{_node_name(node)}'.",
                "Route the loop through a visible user-input block such as Question, or break the cycle.",
                node=node,
                transition=transition,
            ))

        stack.pop()
        stack_set.remove(key)

    for node in nodes:
        if node.node_key not in visited:
            visit(node.node_key)


def validate_flow_version(db: Session, version_id: int) -> dict:
    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if not flow:
        validation_errors = [_error(
            "FLOW_MISSING",
            "Create a flow before testing or publishing this version.",
            "Open the Flow Builder and create a flow for this version.",
        )]
        return {
            "valid": False,
            "errors": [item["message"] for item in validation_errors],
            "validation_errors": validation_errors,
        }

    nodes = db.query(FlowNode).filter(FlowNode.flow_id == flow.id).all()
    transitions = db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).all()
    validation_errors: list[dict] = []

    if not nodes:
        validation_errors = [_error(
            "FLOW_EMPTY",
            "Add at least one block to the flow.",
            "Add a Start block and connect the conversation path.",
        )]
        return {
            "valid": False,
            "errors": [item["message"] for item in validation_errors],
            "validation_errors": validation_errors,
        }

    if len(nodes) > MAX_FLOW_NODES:
        validation_errors.append(_error(
            "MAX_FLOW_NODES_EXCEEDED",
            f"Flow has {len(nodes)} blocks, above the limit of {MAX_FLOW_NODES}.",
            f"Reduce the flow to {MAX_FLOW_NODES} blocks or fewer.",
        ))
    if len(transitions) > MAX_FLOW_TRANSITIONS:
        validation_errors.append(_error(
            "MAX_FLOW_TRANSITIONS_EXCEEDED",
            f"Flow has {len(transitions)} connectors, above the limit of {MAX_FLOW_TRANSITIONS}.",
            f"Reduce the flow to {MAX_FLOW_TRANSITIONS} connectors or fewer.",
        ))

    node_by_key = {node.node_key: node for node in nodes}
    start = node_by_key.get("start")
    if not start:
        validation_errors.append(_error(
            "START_NODE_MISSING",
            "Add a Start block before testing or publishing.",
            "Create one Start block and connect it to the first conversation block.",
        ))

    for node in nodes:
        if not is_valid_canvas_position(node.position_x) or not is_valid_canvas_position(node.position_y):
            validation_errors.append(_error(
                "INVALID_CANVAS_POSITION",
                f"'{_node_name(node)}' has an invalid canvas position.",
                "Move the block inside the supported canvas bounds.",
                node=node,
            ))

    seen_transition_keys: dict[tuple[str, str, str], FlowTransition] = {}
    for transition in transitions:
        if transition.source_node_key not in node_by_key:
            validation_errors.append(_error(
                "BROKEN_TRANSITION_SOURCE",
                f"Remove the broken connector from {transition.source_node_key}.",
                "Reconnect this connector from an existing source block.",
                transition=transition,
            ))
        if transition.target_node_key not in node_by_key:
            validation_errors.append(_error(
                "BROKEN_TRANSITION_TARGET",
                f"Choose a valid next block for the connector from {transition.source_node_key}.",
                "Reconnect this connector to an existing target block.",
                transition=transition,
            ))

        duplicate_key = (
            transition.source_node_key,
            transition.target_node_key,
            normalize_transition_output_key(transition.label, transition.condition),
        )
        if duplicate_key in seen_transition_keys:
            validation_errors.append(_error(
                "DUPLICATE_TRANSITION",
                "Duplicate connector with the same source, target, and output key.",
                "Keep one connector for this output key or route it to a different block.",
                transition=transition,
            ))
        else:
            seen_transition_keys[duplicate_key] = transition

    outgoing: dict[str, list[FlowTransition]] = {}
    incoming: dict[str, list[FlowTransition]] = {}
    for transition in transitions:
        outgoing.setdefault(transition.source_node_key, []).append(transition)
        incoming.setdefault(transition.target_node_key, []).append(transition)

    if start:
        reachable = {start.node_key}
        stack = [start.node_key]
        while stack:
            current = stack.pop()
            for transition in outgoing.get(current, []):
                if transition.target_node_key in node_by_key and transition.target_node_key not in reachable:
                    reachable.add(transition.target_node_key)
                    stack.append(transition.target_node_key)

        for node in nodes:
            if node.node_key not in reachable:
                validation_errors.append(_error(
                    "NODE_UNREACHABLE",
                    f"Connect '{_node_name(node)}' to the Start path.",
                    "Add a connector from the reachable conversation path to this block.",
                    node=node,
                ))

    _add_cycle_errors(validation_errors, nodes, outgoing)

    for node in nodes:
        config = node.config or {}
        if node.node_key != "start" and not incoming.get(node.node_key) and not outgoing.get(node.node_key):
            validation_errors.append(_error(
                "NODE_ISOLATED",
                f"'{_node_name(node)}' is isolated. Connect it to the conversation flow.",
                "Connect this block to another block, or remove it.",
                node=node,
            ))

        if node.type not in {"end", "handoff"} and node.type not in {"buttons", "condition", "rag_answer", *ADVANCED_PLACEHOLDER_TYPES} and not _has_next(outgoing, node):
            validation_errors.append(_error(
                "NEXT_STEP_MISSING",
                f"Choose a next step for '{_node_name(node)}'.",
                "Connect this block to the next block in the conversation.",
                node=node,
            ))

        if node.type == "buttons":
            buttons = [str(item).strip() for item in config.get("buttons", []) if str(item).strip()]
            if not buttons:
                validation_errors.append(_error(
                    "BUTTONS_EMPTY",
                    f"Add at least one button label to '{_node_name(node)}'.",
                    "Add one or more button options.",
                    node=node,
                ))
            for button in buttons:
                has_path = any(
                    transition.target_node_key
                    for transition in outgoing.get(node.node_key, [])
                    if (transition.label or "").strip() == button
                )
                if not has_path:
                    validation_errors.append(_error(
                        "BUTTON_TRANSITION_MISSING",
                        f"Choose a next step for button '{button}' in '{_node_name(node)}'.",
                        "Add one connector for this button option.",
                        node=node,
                    ))

        if node.type == "condition":
            labels = {
                normalize_transition_output_key(transition.label, transition.condition)
                for transition in outgoing.get(node.node_key, [])
            }
            if "true" not in labels:
                validation_errors.append(_error(
                    "CONDITION_TRUE_MISSING",
                    f"Choose the True path for condition '{_node_name(node)}'.",
                    "Add a connector labeled True.",
                    node=node,
                ))
            if "false" not in labels:
                validation_errors.append(_error(
                    "CONDITION_FALSE_MISSING",
                    f"Choose the False path for condition '{_node_name(node)}'.",
                    "Add a connector labeled False.",
                    node=node,
                ))

        if node.type in {"rag_answer", "knowledge_search"}:
            if not str(config.get("fallback") or "").strip():
                validation_errors.append(_error(
                    "RAG_FALLBACK_MISSING",
                    f"Add a fallback message to AI/RAG block '{_node_name(node)}'.",
                    "Configure a fallback response for low-confidence or failed retrieval.",
                    node=node,
                ))

            has_self_loop = any(
                transition.target_node_key == node.node_key
                for transition in outgoing.get(node.node_key, [])
            )
            has_any_next_step = bool(outgoing.get(node.node_key))
            if not _has_continue_rag(node) and not has_self_loop and not has_any_next_step:
                validation_errors.append(_error(
                    "RAG_CONTINUATION_MISSING",
                    f"Enable continuous AI/RAG answers or connect a next step for '{_node_name(node)}'.",
                    "Enable continuation, add a self-loop, or connect a fallback/next step.",
                    node=node,
                ))

        if node.type in {"question", "collect_name", "collect_email", "collect_phone"}:
            if not str(config.get("field") or "").strip():
                validation_errors.append(_error(
                    "INPUT_VARIABLE_MISSING",
                    f"Add a variable name to '{_node_name(node)}'.",
                    "Set the variable that stores the user response.",
                    node=node,
                ))

        if node.type == "collect_email" and not str(config.get("field") or "").strip():
            validation_errors.append(_error(
                "EMAIL_VARIABLE_MISSING",
                f"Collect Email block '{_node_name(node)}' needs an email variable.",
                "Set the email variable name, for example user_email.",
                node=node,
            ))

        if node.type == "set_variable":
            if not str(config.get("field") or "").strip():
                validation_errors.append(_error(
                    "SET_VARIABLE_NAME_MISSING",
                    f"Add the variable name for Set Variable block '{_node_name(node)}'.",
                    "Set the variable name to write.",
                    node=node,
                ))
            if "value" not in config and "expression" not in config:
                validation_errors.append(_error(
                    "SET_VARIABLE_VALUE_MISSING",
                    f"Add the value for Set Variable block '{_node_name(node)}'.",
                    "Set a literal value or expression.",
                    node=node,
                ))

        if node.type == "api_request":
            method = str(config.get("method") or "GET").upper()
            if method not in {"GET", "POST"}:
                validation_errors.append(_error(
                    "API_METHOD_INVALID",
                    f"Choose GET or POST for API block '{_node_name(node)}'.",
                    "Set the API method to GET or POST.",
                    node=node,
                ))
            if not is_valid_http_url(str(config.get("url") or "")):
                validation_errors.append(_error(
                    "API_URL_INVALID",
                    f"Add a valid URL to API block '{_node_name(node)}'.",
                    "Use a full http:// or https:// URL.",
                    node=node,
                ))
            if not _valid_timeout(config.get("timeout")):
                validation_errors.append(_error(
                    "API_TIMEOUT_INVALID",
                    f"Set a valid timeout for API block '{_node_name(node)}'.",
                    "Use a timeout between 1 and 30 seconds.",
                    node=node,
                ))

        if node.type == "meeting_scheduler" and not str(config.get("field") or "").strip():
            validation_errors.append(_error(
                "MEETING_VARIABLE_MISSING",
                f"Add the meeting time variable for '{_node_name(node)}'.",
                "Set the variable that stores the preferred meeting time.",
                node=node,
            ))

        if node.type == "handoff":
            email_field = str(config.get("email_field") or "").strip()
            phone_field = str(config.get("phone_field") or "").strip()
            collect_missing = bool(config.get("collect_email_if_missing") or config.get("collect_phone_if_missing"))
            team_method = str(config.get("department") or config.get("team") or "").strip()
            if not email_field and not phone_field and not collect_missing and not team_method:
                validation_errors.append(_error(
                    "HANDOFF_CONTACT_MISSING",
                    f"Choose at least one contact method for handoff block '{_node_name(node)}'.",
                    "Configure an email field, phone field, collection prompt, team, or department.",
                    node=node,
                ))

        if node.type == "ai_router":
            if not _string_items(config.get("routes")):
                validation_errors.append(_error(
                    "AI_ROUTER_ROUTES_MISSING",
                    f"Add valid routes to AI Router block '{_node_name(node)}'.",
                    "Configure at least one non-empty route.",
                    node=node,
                ))

        if node.type == "ai_classifier":
            if not _string_items(config.get("categories")):
                validation_errors.append(_error(
                    "AI_CLASSIFIER_CATEGORIES_MISSING",
                    f"Add valid categories to AI Classifier block '{_node_name(node)}'.",
                    "Configure at least one non-empty category.",
                    node=node,
                ))

    unique_errors = _dedupe_errors(validation_errors)
    return {
        "valid": len(unique_errors) == 0,
        "errors": [item["message"] for item in unique_errors],
        "validation_errors": unique_errors,
    }
