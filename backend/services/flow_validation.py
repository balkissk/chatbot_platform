from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition


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


def validate_flow_version(db: Session, version_id: int) -> dict:
    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if not flow:
        return {
            "valid": False,
            "errors": ["Create a flow before testing or publishing this version."]
        }

    nodes = db.query(FlowNode).filter(FlowNode.flow_id == flow.id).all()
    transitions = db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).all()
    errors: list[str] = []

    if not nodes:
        return {
            "valid": False,
            "errors": ["Add at least one block to the flow."]
        }

    node_by_key = {node.node_key: node for node in nodes}
    start = node_by_key.get("start")
    if not start:
        errors.append("Add a Start block before testing or publishing.")

    for transition in transitions:
        if transition.source_node_key not in node_by_key:
            errors.append(f"Remove the broken connector from {transition.source_node_key}.")
        if transition.target_node_key not in node_by_key:
            errors.append(f"Choose a valid next block for the connector from {transition.source_node_key}.")

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
                errors.append(f"Connect '{_node_name(node)}' to the Start path.")

    for node in nodes:
        config = node.config or {}
        if node.node_key != "start" and not incoming.get(node.node_key) and not outgoing.get(node.node_key):
            errors.append(f"'{_node_name(node)}' is isolated. Connect it to the conversation flow.")

        if node.type not in {"end", "handoff"} and node.type not in {"buttons", "condition", "rag_answer"} and not _has_next(outgoing, node):
            errors.append(f"Choose a next step for '{_node_name(node)}'.")

        if node.type == "buttons":
            buttons = [str(item).strip() for item in config.get("buttons", []) if str(item).strip()]
            if not buttons:
                errors.append(f"Add at least one button label to '{_node_name(node)}'.")
            for button in buttons:
                has_path = any(
                    transition.target_node_key
                    for transition in outgoing.get(node.node_key, [])
                    if (transition.label or "").strip() == button
                )
                if not has_path:
                    errors.append(f"Choose a next step for button '{button}' in '{_node_name(node)}'.")

        if node.type == "condition":
            labels = {_normalized(transition.label) for transition in outgoing.get(node.node_key, [])}
            if "true" not in labels:
                errors.append(f"Choose the True path for condition '{_node_name(node)}'.")
            if "false" not in labels:
                errors.append(f"Choose the False path for condition '{_node_name(node)}'.")

        if node.type == "rag_answer":
            if not str(config.get("fallback") or "").strip():
                errors.append(f"Add a fallback message to AI/RAG block '{_node_name(node)}'.")

            has_self_loop = any(
                transition.target_node_key == node.node_key
                for transition in outgoing.get(node.node_key, [])
            )
            has_any_next_step = bool(outgoing.get(node.node_key))
            if not _has_continue_rag(node) and not has_self_loop and not has_any_next_step:
                errors.append(
                    f"Enable continuous AI/RAG answers or connect a next step for '{_node_name(node)}'."
                )

        if node.type in {"question", "collect_name", "collect_email", "collect_phone"}:
            if not str(config.get("field") or "").strip():
                errors.append(f"Add a variable name to '{_node_name(node)}'.")

        if node.type == "collect_email" and not str(config.get("field") or "").strip():
            errors.append(f"Collect Email block '{_node_name(node)}' needs an email variable.")

        if node.type == "set_variable":
            if not str(config.get("field") or "").strip():
                errors.append(f"Add the variable name for Set Variable block '{_node_name(node)}'.")
            if "value" not in config:
                errors.append(f"Add the value for Set Variable block '{_node_name(node)}'.")

        if node.type == "api_request":
            method = str(config.get("method") or "GET").upper()
            if method not in {"GET", "POST"}:
                errors.append(f"Choose GET or POST for API block '{_node_name(node)}'.")
            if not str(config.get("url") or "").strip():
                errors.append(f"Add a URL to API block '{_node_name(node)}'.")

        if node.type == "handoff":
            email_field = str(config.get("email_field") or "").strip()
            phone_field = str(config.get("phone_field") or "").strip()
            collect_missing = bool(config.get("collect_email_if_missing") or config.get("collect_phone_if_missing"))
            if not email_field and not phone_field and not collect_missing:
                errors.append(f"Choose at least one contact method for handoff block '{_node_name(node)}'.")

    unique_errors = list(dict.fromkeys(errors))
    return {
        "valid": len(unique_errors) == 0,
        "errors": unique_errors
    }
