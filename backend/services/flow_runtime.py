from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def _first_transition(transitions: list[FlowTransition], source_key: str) -> FlowTransition | None:
    return next(
        (transition for transition in transitions if transition.source_node_key == source_key),
        None
    )


def _matching_transition(
    transitions: list[FlowTransition],
    source_key: str,
    message: str
) -> FlowTransition | None:
    message_value = _normalized(message)
    candidates = [
        transition
        for transition in transitions
        if transition.source_node_key == source_key
    ]

    for transition in candidates:
        if _normalized(transition.label) == message_value:
            return transition

    return candidates[0] if len(candidates) == 1 else None


def _node_text(node: FlowNode) -> str:
    config = node.config or {}
    return config.get("text") or config.get("prompt") or config.get("message") or node.label


def _options_for(node: FlowNode, transitions: list[FlowTransition]) -> list[str]:
    config = node.config or {}
    buttons = config.get("buttons") or []
    transition_labels = [
        transition.label
        for transition in transitions
        if transition.source_node_key == node.node_key and transition.label
    ]

    return buttons or transition_labels


def _is_negative_feedback(value: str | None) -> bool:
    return _normalized(value) in {"no", "not helpful", "bad", "nope", "non", "no thanks"}


def _is_positive_feedback(value: str | None) -> bool:
    return _normalized(value) in {"yes", "helpful", "good", "thanks", "oui"}


def _to_number(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _evaluate_condition(config: dict, variables: dict) -> bool:
    field = config.get("field")
    operator = config.get("operator") or "equals"
    expected = config.get("value")
    actual = variables.get(field) if field else None

    actual_text = str(actual or "").strip()
    expected_text = str(expected or "").strip()
    actual_norm = _normalized(actual_text)
    expected_norm = _normalized(expected_text)

    if operator == "exists":
        return actual is not None and actual_text != ""
    if operator == "not_exists":
        return actual is None or actual_text == ""
    if operator == "equals":
        return actual_norm == expected_norm
    if operator == "not_equals":
        return actual_norm != expected_norm
    if operator == "contains":
        return expected_norm in actual_norm
    if operator == "not_contains":
        return expected_norm not in actual_norm

    actual_number = _to_number(actual)
    expected_number = _to_number(expected)
    if actual_number is None or expected_number is None:
        return False

    if operator in {"greater_than", "gt"}:
        return actual_number > expected_number
    if operator in {"greater_or_equal", "gte"}:
        return actual_number >= expected_number
    if operator in {"less_than", "lt"}:
        return actual_number < expected_number
    if operator in {"less_or_equal", "lte"}:
        return actual_number <= expected_number

    return False


def _transition_by_label(
    transitions: list[FlowTransition],
    source_key: str,
    labels: set[str]
) -> FlowTransition | None:
    return next(
        (
            transition
            for transition in transitions
            if transition.source_node_key == source_key
            and _normalized(transition.label) in labels
        ),
        None
    )


def _execute_action(node: FlowNode, variables: dict) -> tuple[str, bool]:
    config = node.config or {}
    action_type = config.get("action_type") or config.get("action") or "set_variable"

    if action_type == "set_variable":
        field = (config.get("field") or "").strip()
        if field:
            variables[field] = config.get("value", "")
        return config.get("message") or _node_text(node), False

    if action_type == "handoff":
        variables["__handoff_requested"] = True
        variables["__handoff_reason"] = config.get("reason") or variables.get("__last_input") or ""
        return config.get("message") or "A teammate will review this conversation.", True

    if action_type == "end":
        variables["__ended"] = True
        return config.get("message") or "The conversation is now closed.", True

    return _node_text(node), False


def _serialize_state(
    response: str,
    current_node_key: str | None,
    variables: dict,
    options: list[str] | None = None,
    sources: list[dict] | None = None,
    used: str = "flow",
    messages: list[dict] | None = None
) -> dict:
    return {
        "response": response,
        "messages": messages or [{"text": response, "options": options or []}],
        "mode_used": used,
        "current_node_key": current_node_key,
        "variables": variables,
        "options": options or [],
        "sources": sources or []
    }


def execute_flow(
    db: Session,
    version_id: int,
    message: str,
    current_node_key: str | None,
    variables: dict | None,
    rag_answer=None,
    allow_rag_fallback: bool = False
) -> dict:
    flow = db.query(Flow).filter(Flow.version_id == version_id).first()
    if not flow:
        return _serialize_state(
            "This chatbot does not have a flow yet.",
            None,
            variables or {},
            used="flow"
        )

    nodes = db.query(FlowNode).filter(FlowNode.flow_id == flow.id).all()
    transitions = db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).all()
    node_by_key = {node.node_key: node for node in nodes}
    state = variables or {}

    node = node_by_key.get(current_node_key or "start")
    if not node and nodes:
        node = nodes[0]

    if not node:
        return _serialize_state("This flow is empty.", None, state)

    # Start/message nodes display text first, then wait at the next step.
    if node.type == "message":
        transition = _first_transition(transitions, node.node_key)
        next_key = transition.target_node_key if transition else None
        next_node = node_by_key.get(next_key)
        if next_node and next_node.type in {"question", "buttons"}:
            next_text = _node_text(next_node)
            options = _options_for(next_node, transitions)
            return _serialize_state(
                next_text,
                next_node.node_key,
                state,
                options,
                messages=[
                    {"text": _node_text(node), "options": []},
                    {"text": next_text, "options": options}
                ]
            )

        return _serialize_state(_node_text(node), next_key, state)

    if node.type == "question":
        field = (node.config or {}).get("field") or node.node_key
        if message.strip():
            state[field] = message.strip()
            state["__last_input"] = message.strip()
            state["__last_question"] = message.strip()
            transition = _first_transition(transitions, node.node_key)
            next_key = transition.target_node_key if transition else None
            next_node = node_by_key.get(next_key)
            if next_node:
                return execute_flow(
                    db,
                    version_id,
                    "",
                    next_node.node_key,
                    state,
                    rag_answer=rag_answer,
                    allow_rag_fallback=allow_rag_fallback
                )

        return _serialize_state(_node_text(node), node.node_key, state)

    if node.type == "buttons":
        options = _options_for(node, transitions)
        if not message.strip():
            return _serialize_state(_node_text(node), node.node_key, state, options)

        transition = _matching_transition(transitions, node.node_key, message)
        if not transition:
            if allow_rag_fallback and rag_answer:
                return rag_answer(message, state)
            return _serialize_state(
                "Choose one of the available options.",
                node.node_key,
                state,
                options
            )

        field = (node.config or {}).get("field")
        selected_value = transition.label or message
        if field:
            state[field] = selected_value
        state["__last_input"] = selected_value
        if _is_negative_feedback(selected_value):
            state["__feedback"] = "not_helpful"
        elif _is_positive_feedback(selected_value):
            state["__feedback"] = "helpful"

        return execute_flow(
            db,
            version_id,
            "",
            transition.target_node_key,
            state,
            rag_answer=rag_answer,
            allow_rag_fallback=allow_rag_fallback
        )

    if node.type == "rag_answer":
        if rag_answer:
            transition = _first_transition(transitions, node.node_key)
            query = message.strip() or state.get("__last_question") or state.get("__last_input") or ""
            result = rag_answer(query, state)
            state["__last_ai_answer"] = result.get("response", "")
            result["variables"] = state
            next_key = transition.target_node_key if transition else None
            next_node = node_by_key.get(next_key)

            if next_node and next_node.type in {"question", "buttons"}:
                next_text = _node_text(next_node)
                options = _options_for(next_node, transitions)
                messages = result.get("messages") or [
                    {"text": result.get("response", ""), "options": []}
                ]
                result["messages"] = [
                    *messages,
                    {"text": next_text, "options": options}
                ]
                result["options"] = options
                result["current_node_key"] = next_node.node_key
                return result

            result["current_node_key"] = next_key
            return result
        return _serialize_state("RAG is not configured for this chatbot.", node.node_key, state)

    if node.type == "condition":
        matched = _evaluate_condition(node.config or {}, state)
        transition = _transition_by_label(
            transitions,
            node.node_key,
            {"true", "yes", "matched"} if matched else {"false", "no", "else"}
        )
        if not transition:
            transition = _first_transition(transitions, node.node_key)

        if not transition:
            return _serialize_state(_node_text(node), node.node_key, state)

        return execute_flow(
            db,
            version_id,
            "",
            transition.target_node_key,
            state,
            rag_answer=rag_answer,
            allow_rag_fallback=allow_rag_fallback
        )

    if node.type == "action":
        response, stop_here = _execute_action(node, state)
        if stop_here:
            return _serialize_state(response, None, state, used="action")

        transition = _first_transition(transitions, node.node_key)
        next_key = transition.target_node_key if transition else None
        if next_key:
            return execute_flow(
                db,
                version_id,
                "",
                next_key,
                state,
                rag_answer=rag_answer,
                allow_rag_fallback=allow_rag_fallback
            )
        return _serialize_state(response, None, state, used="action")

    if node.type == "handoff":
        state["__handoff_requested"] = True
        state["__handoff_reason"] = state.get("__last_input") or ""
        return _serialize_state(_node_text(node), None, state, used="handoff")

    if node.type == "end":
        state["__ended"] = True
        return _serialize_state(_node_text(node), None, state, used="end")

    if allow_rag_fallback and rag_answer:
        return rag_answer(message, state)

    return _serialize_state(_node_text(node), node.node_key, state)
