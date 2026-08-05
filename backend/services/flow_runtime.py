import ipaddress
import re
import time
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from models.flow import Flow, FlowNode, FlowTransition
from services.flow_limits import MAX_RUNTIME_STEPS


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


def _exact_transition(
    transitions: list[FlowTransition],
    source_key: str,
    message: str
) -> FlowTransition | None:
    message_value = _normalized(message)
    if not message_value:
        return None

    return next(
        (
            transition
            for transition in transitions
            if transition.source_node_key == source_key
            and _normalized(transition.label) == message_value
        ),
        None
    )


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


def _continues_rag(node: FlowNode) -> bool:
    config = node.config or {}
    return bool(
        config.get("continue_rag")
        or config.get("continue_answering")
        or config.get("continue_ai_rag")
    )


def _truthy_config(value) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized(str(value)) in {"1", "true", "yes", "on"}


def _is_silent_input(node: FlowNode) -> bool:
    config = node.config or {}
    return any(
        _truthy_config(config.get(key))
        for key in ("silent", "silent_input", "hide_prompt", "hide_message")
    )


def _requests_human(message: str) -> bool:
    text = _normalized(message)
    return any(
        phrase in text
        for phrase in (
            "human",
            "agent",
            "support team",
            "real person",
            "talk to someone",
            "speak to someone",
            "contact support",
            "escalate",
        )
    )


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


def _valid_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def _valid_phone(value: str) -> bool:
    compact = re.sub(r"[\s().-]+", "", value.strip())
    return bool(re.match(r"^\+?[0-9]{7,15}$", compact))


def _is_safe_webhook_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return True


def _render_template_value(value, variables: dict):
    if isinstance(value, dict):
        return {key: _render_template_value(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template_value(item, variables) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match):
        return str(variables.get(match.group(1), ""))

    return re.sub(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}", replace, value)


def _runtime_language(variables: dict | None) -> str:
    return "fr" if _normalized((variables or {}).get("__language")) == "fr" else "en"


def _runtime_message(key: str, variables: dict | None = None) -> str:
    messages = {
        "en": {
            "no_flow": "This chatbot does not have a flow yet.",
            "empty_flow": "This flow is empty.",
            "invalid_email": "Please enter a valid email address.",
            "invalid_phone": "Please enter a valid phone number.",
            "choose_option": "Choose one of the available options.",
            "teammate_review": "A teammate will review this conversation.",
            "conversation_closed": "The conversation is now closed.",
            "collect_email": "What email should our team use to contact you?",
            "collect_phone": "What phone number should our team use to contact you?",
            "external_bad_method": "The external request is not configured correctly.",
            "external_bad_url": "The external request URL is missing or unsafe.",
            "external_error": "The external service returned an error.",
            "external_unreachable": "The external service could not be reached.",
            "runtime_loop": "This conversation flow could not complete safely.",
        },
        "fr": {
            "no_flow": "Cet assistant n'a pas encore de flow.",
            "empty_flow": "Ce flow est vide.",
            "invalid_email": "Veuillez saisir une adresse email valide.",
            "invalid_phone": "Veuillez saisir un numero de telephone valide.",
            "choose_option": "Choisissez l'une des options disponibles.",
            "teammate_review": "Un membre de l'equipe examinera cette conversation.",
            "conversation_closed": "La conversation est maintenant fermee.",
            "collect_email": "Quel email notre equipe doit-elle utiliser pour vous contacter ?",
            "collect_phone": "Quel numero de telephone notre equipe doit-elle utiliser pour vous contacter ?",
            "external_bad_method": "La requete externe n'est pas configuree correctement.",
            "external_bad_url": "L'URL de la requete externe est manquante ou non securisee.",
            "external_error": "Le service externe a renvoye une erreur.",
            "external_unreachable": "Le service externe est injoignable.",
            "runtime_loop": "Ce flow de conversation n'a pas pu se terminer en securite.",
        },
    }
    language = _runtime_language(variables)
    return messages[language][key]


def _execute_api_request(node: FlowNode, variables: dict) -> tuple[str, bool]:
    config = node.config or {}
    method = str(config.get("method") or "GET").upper()
    url = str(config.get("url") or "").strip()
    response_field = str(config.get("response_field") or "").strip()
    try:
        timeout = float(config.get("timeout") or 8)
    except (TypeError, ValueError):
        timeout = 8
    timeout = min(max(timeout, 1), 30)

    if method not in {"GET", "POST"}:
        variables["__last_api_error"] = "Unsupported API method"
        return config.get("error_message") or _runtime_message("external_bad_method", variables), False
    if not url or not _is_safe_webhook_url(url):
        variables["__last_api_error"] = "Unsafe or missing API URL"
        return config.get("error_message") or _runtime_message("external_bad_url", variables), False

    headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    body = config.get("body") if isinstance(config.get("body"), dict) else None
    rendered_headers = {str(key): str(_render_template_value(value, variables)) for key, value in headers.items()}
    rendered_body = _render_template_value(body, variables) if body is not None else None

    try:
        response = requests.request(
            method,
            url,
            headers=rendered_headers,
            json=rendered_body if method == "POST" else None,
            timeout=timeout,
        )
        variables["__last_api_status"] = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = response.text[:1000]
        variables["__last_api_response"] = payload
        if response_field:
            variables[response_field] = payload
        if not response.ok:
            variables["__last_api_error"] = f"HTTP {response.status_code}"
            return config.get("error_message") or _runtime_message("external_error", variables), False
    except requests.RequestException as exc:
        variables["__last_api_error"] = str(exc)
        return config.get("error_message") or _runtime_message("external_unreachable", variables), False

    return config.get("success_message") or _node_text(node), False


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
        return config.get("message") or _runtime_message("teammate_review", variables), True

    if action_type == "end":
        variables["__ended"] = True
        return config.get("message") or _runtime_message("conversation_closed", variables), True

    return _node_text(node), False


def _mark_handoff(node: FlowNode, variables: dict) -> str:
    config = node.config or {}
    variables["__handoff_requested"] = True
    variables["__handoff_department"] = config.get("department") or "Support"
    variables["__handoff_reason"] = config.get("reason") or variables.get("__last_input") or ""
    variables["__handoff_contact_email"] = variables.get(config.get("email_field") or "user_email") or variables.get("email") or ""
    variables["__handoff_contact_phone"] = variables.get(config.get("phone_field") or "user_phone") or variables.get("phone") or ""
    return config.get("message") or _runtime_message("teammate_review", variables)


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
        "messages": messages if messages is not None else [{"text": response, "options": options or []}],
        "mode_used": used,
        "current_node_key": current_node_key,
        "variables": variables,
        "options": options or [],
        "sources": sources or []
    }


def _runtime_error_state(node: FlowNode | None, variables: dict, current_node_key: str | None = None) -> dict:
    response = _runtime_message("runtime_loop", variables)
    result = _serialize_state(
        response,
        current_node_key or (node.node_key if node else None),
        variables,
        options=[],
        used="flow_error",
    )
    result["runtime_error"] = {
        "code": "MAX_RUNTIME_STEPS_EXCEEDED",
        "severity": "error",
        "node_id": node.id if node else None,
        "transition_id": None,
        "message": f"Flow execution stopped after {MAX_RUNTIME_STEPS} runtime steps.",
        "suggested_fix": "Break the loop or route it through a visible user-input block.",
    }
    return result


def _add_trace_ms(trace: dict | None, key: str, value: int) -> None:
    if trace is not None:
        trace[key] = int(trace.get(key, 0) or 0) + value


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def execute_flow(
    db: Session,
    version_id: int,
    message: str,
    current_node_key: str | None,
    variables: dict | None,
    rag_answer=None,
    allow_rag_fallback: bool = False,
    trace: dict | None = None,
    _runtime_graph: tuple[Flow, list[FlowNode], list[FlowTransition]] | None = None,
    _runtime_steps: int = 0,
) -> dict:
    if trace is not None:
        trace["flow_invocations"] = int(trace.get("flow_invocations", 0) or 0) + 1

    if _runtime_graph is None:
        db_started_at = time.perf_counter()
        flow = db.query(Flow).filter(Flow.version_id == version_id).first()
        _add_trace_ms(trace, "flow_db_query_ms", _elapsed_ms(db_started_at))
    else:
        flow = _runtime_graph[0]

    if not flow:
        return _serialize_state(
            _runtime_message("no_flow", variables),
            None,
            variables or {},
            used="flow"
        )

    if _runtime_graph is None:
        db_started_at = time.perf_counter()
        nodes = db.query(FlowNode).filter(FlowNode.flow_id == flow.id).all()
        transitions = db.query(FlowTransition).filter(FlowTransition.flow_id == flow.id).all()
        _add_trace_ms(trace, "flow_db_query_ms", _elapsed_ms(db_started_at))
        _runtime_graph = (flow, nodes, transitions)
    else:
        nodes = _runtime_graph[1]
        transitions = _runtime_graph[2]

    node_by_key = {node.node_key: node for node in nodes}
    state = variables or {}

    node = node_by_key.get(current_node_key or "start")
    if not node and nodes:
        node = nodes[0]

    if not node:
        return _serialize_state(_runtime_message("empty_flow", state), None, state)

    if _runtime_steps >= MAX_RUNTIME_STEPS:
        return _runtime_error_state(node, state)

    if trace is not None:
        trace.setdefault("visited_nodes", []).append({
            "node_key": node.node_key,
            "type": node.type,
            "label": node.label,
        })

    # Start/message nodes display text first, then wait at the next step.
    if node.type == "message":
        transition = _first_transition(transitions, node.node_key)
        next_key = transition.target_node_key if transition else None
        next_node = node_by_key.get(next_key)
        if next_node and next_node.type in {"question", "buttons"}:
            if _is_silent_input(next_node):
                return _serialize_state(
                    _node_text(node),
                    next_node.node_key,
                    state,
                    messages=[
                        {"text": _node_text(node), "options": []}
                    ]
                )
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
                    allow_rag_fallback=allow_rag_fallback,
                    trace=trace,
                    _runtime_graph=_runtime_graph,
                    _runtime_steps=_runtime_steps + 1,
                )

        if _is_silent_input(node):
            return _serialize_state(
                "",
                node.node_key,
                state,
                messages=[]
            )

        return _serialize_state(_node_text(node), node.node_key, state)

    if node.type in {"collect_name", "collect_email", "collect_phone"}:
        config = node.config or {}
        default_fields = {
            "collect_name": "user_name",
            "collect_email": "user_email",
            "collect_phone": "user_phone",
        }
        field = config.get("field") or default_fields[node.type]
        clean_message = message.strip()
        if clean_message:
            if node.type == "collect_email" and not _valid_email(clean_message):
                return _serialize_state(
                    config.get("invalid_message") or _runtime_message("invalid_email", state),
                    node.node_key,
                    state
                )
            if node.type == "collect_phone" and not _valid_phone(clean_message):
                return _serialize_state(
                    config.get("invalid_message") or _runtime_message("invalid_phone", state),
                    node.node_key,
                    state
                )

            state[field] = clean_message
            state["__last_input"] = clean_message
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
                    allow_rag_fallback=allow_rag_fallback,
                    trace=trace,
                    _runtime_graph=_runtime_graph,
                    _runtime_steps=_runtime_steps + 1,
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
                _runtime_message("choose_option", state),
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
            allow_rag_fallback=allow_rag_fallback,
            trace=trace,
            _runtime_graph=_runtime_graph,
            _runtime_steps=_runtime_steps + 1,
        )

    if node.type == "knowledge_search" and _truthy_config((node.config or {}).get("retrieval_only")):
        if rag_answer:
            transition = _first_transition(transitions, node.node_key)
            next_key = transition.target_node_key if transition else None
            next_node = node_by_key.get(next_key)
            query = message.strip() or state.get("__last_question") or state.get("__last_input") or ""
            if next_node and next_node.type == "rag_answer":
                state["__knowledge_search_skipped"] = True
                if message.strip():
                    state["__last_input"] = message.strip()
                    state["__last_question"] = message.strip()
                return execute_flow(
                    db,
                    version_id,
                    "",
                    next_key,
                    state,
                    rag_answer=rag_answer,
                    allow_rag_fallback=allow_rag_fallback,
                    trace=trace,
                    _runtime_graph=_runtime_graph,
                    _runtime_steps=_runtime_steps + 1,
                )
            try:
                result = rag_answer(query, state, node.config or {})
            except TypeError:
                result = rag_answer(query, state)

            state["__knowledge_search_answer"] = result.get("response", "")
            state["__knowledge_search_sources"] = result.get("sources", [])
            state["__knowledge_search_mode"] = result.get("retrieval_mode", "")
            if message.strip():
                state["__last_input"] = message.strip()
                state["__last_question"] = message.strip()

            if next_key:
                return execute_flow(
                    db,
                    version_id,
                    "",
                    next_key,
                    state,
                    rag_answer=rag_answer,
                    allow_rag_fallback=allow_rag_fallback,
                    trace=trace,
                    _runtime_graph=_runtime_graph,
                    _runtime_steps=_runtime_steps + 1,
                )

            return _serialize_state("", node.node_key, state, messages=[])
        return _serialize_state("RAG is not configured for this chatbot.", node.node_key, state)

    if node.type in {"rag_answer", "knowledge_search"}:
        if rag_answer:
            transition = _first_transition(transitions, node.node_key)
            query = message.strip() or state.get("__last_question") or state.get("__last_input") or ""

            if _continues_rag(node):
                explicit_transition = _exact_transition(transitions, node.node_key, message)
                if explicit_transition and explicit_transition.target_node_key != node.node_key:
                    state["__last_input"] = message.strip()
                    return execute_flow(
                        db,
                        version_id,
                        "",
                        explicit_transition.target_node_key,
                        state,
                        rag_answer=rag_answer,
                        allow_rag_fallback=allow_rag_fallback,
                        trace=trace,
                        _runtime_graph=_runtime_graph,
                        _runtime_steps=_runtime_steps + 1,
                    )

            try:
                result = rag_answer(query, state, node.config or {})
            except TypeError:
                result = rag_answer(query, state)
            state["__last_ai_answer"] = result.get("response", "")
            if message.strip():
                state["__last_input"] = message.strip()
                state["__last_question"] = message.strip()
            result["variables"] = state

            if _continues_rag(node):
                result["current_node_key"] = node.node_key
                return result

            next_key = transition.target_node_key if transition else None
            next_node = node_by_key.get(next_key)
            fallback_transition = next(
                (
                    item for item in transitions
                    if item.source_node_key == node.node_key
                    and _normalized(item.label) in {"fallback", "handoff", "low_confidence"}
                ),
                None
            )
            should_handoff = bool(
                fallback_transition
                and (
                    _requests_human(message or state.get("__last_question") or state.get("__last_input") or "")
                    or result.get("mode_used") == "fallback"
                )
            )
            if should_handoff:
                handoff_result = execute_flow(
                    db,
                    version_id,
                    "",
                    fallback_transition.target_node_key,
                    state,
                    rag_answer=rag_answer,
                    allow_rag_fallback=allow_rag_fallback,
                    trace=trace,
                    _runtime_graph=_runtime_graph,
                    _runtime_steps=_runtime_steps + 1,
                )
                result_messages = result.get("messages") or [{"text": result.get("response", ""), "options": []}]
                handoff_messages = handoff_result.get("messages") or []
                result["messages"] = [*result_messages, *handoff_messages]
                result["options"] = handoff_result.get("options") or []
                result["current_node_key"] = handoff_result.get("current_node_key")
                result["variables"] = handoff_result.get("variables") or state
                result["mode_used"] = handoff_result.get("mode_used") or result.get("mode_used")
                return result

            if next_node and next_node.type in {"question", "buttons"}:
                if _is_silent_input(next_node):
                    result["options"] = []
                    result["current_node_key"] = next_node.node_key
                    return result
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

    if node.type == "meeting_scheduler":
        config = node.config or {}
        field = config.get("field") or "preferred_time"
        clean_message = message.strip()
        if clean_message:
            state[field] = clean_message
            state["__last_input"] = clean_message
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
                    allow_rag_fallback=allow_rag_fallback,
                    trace=trace,
                    _runtime_graph=_runtime_graph,
                    _runtime_steps=_runtime_steps + 1,
                )
            return _serialize_state(
                config.get("success_message") or "Meeting preference saved.",
                node.node_key,
                state
            )

        return _serialize_state(_node_text(node), node.node_key, state)

    if node.type in {"ai_router", "ai_classifier", "confidence_check", "lead_score"}:
        config = node.config or {}
        if node.type in {"ai_router", "ai_classifier"}:
            output_variable = config.get("output_variable") or "detected_intent"
            state[output_variable] = state.get("__last_input") or "general"
        if node.type == "lead_score":
            state[config.get("score_variable") or "lead_score"] = config.get("default_score", 50)
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
                allow_rag_fallback=allow_rag_fallback,
                trace=trace,
                _runtime_graph=_runtime_graph,
                _runtime_steps=_runtime_steps + 1,
            )
        return _serialize_state(config.get("message") or _node_text(node), node.node_key, state)

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
            allow_rag_fallback=allow_rag_fallback,
            trace=trace,
            _runtime_graph=_runtime_graph,
            _runtime_steps=_runtime_steps + 1,
        )

    if node.type in {"action", "set_variable"}:
        if node.type == "set_variable":
            node.config = {**(node.config or {}), "action_type": "set_variable"}
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
                allow_rag_fallback=allow_rag_fallback,
                trace=trace,
                _runtime_graph=_runtime_graph,
                _runtime_steps=_runtime_steps + 1,
            )
        return _serialize_state(response, None, state, used="action")

    if node.type == "api_request":
        response, _ = _execute_api_request(node, state)
        transition = _first_transition(transitions, node.node_key)
        next_key = transition.target_node_key if transition else None
        if next_key:
            next_result = execute_flow(
                db,
                version_id,
                "",
                next_key,
                state,
                rag_answer=rag_answer,
                allow_rag_fallback=allow_rag_fallback,
                trace=trace,
                _runtime_graph=_runtime_graph,
                _runtime_steps=_runtime_steps + 1,
            )
            messages = [{"text": response, "options": []}]
            messages.extend(next_result.get("messages") or [])
            next_result["messages"] = messages
            next_result["response"] = next_result.get("response") or response
            return next_result
        return _serialize_state(response, None, state, used="api_request")

    if node.type == "handoff":
        config = node.config or {}
        email_field = config.get("email_field") or "user_email"
        phone_field = config.get("phone_field") or "user_phone"
        collecting = state.get("__handoff_collecting")
        clean_message = message.strip()

        if collecting == "email" and clean_message:
            if not _valid_email(clean_message):
                return _serialize_state(
                    config.get("invalid_email_message") or _runtime_message("invalid_email", state),
                    node.node_key,
                    state
                )
            state[email_field] = clean_message
            state.pop("__handoff_collecting", None)

        if collecting == "phone" and clean_message:
            if not _valid_phone(clean_message):
                return _serialize_state(
                    config.get("invalid_phone_message") or _runtime_message("invalid_phone", state),
                    node.node_key,
                    state
                )
            state[phone_field] = clean_message
            state.pop("__handoff_collecting", None)

        if config.get("collect_email_if_missing") and not state.get(email_field):
            state["__handoff_collecting"] = "email"
            return _serialize_state(
                config.get("collect_email_prompt") or _runtime_message("collect_email", state),
                node.node_key,
                state
            )

        if config.get("collect_phone_if_missing") and not state.get(phone_field):
            state["__handoff_collecting"] = "phone"
            return _serialize_state(
                config.get("collect_phone_prompt") or _runtime_message("collect_phone", state),
                node.node_key,
                state
            )

        return _serialize_state(_mark_handoff(node, state), None, state, used="handoff")

    if node.type == "end":
        state["__ended"] = True
        return _serialize_state(_node_text(node), None, state, used="end")

    if allow_rag_fallback and rag_answer:
        return rag_answer(message, state)

    return _serialize_state(_node_text(node), node.node_key, state)
