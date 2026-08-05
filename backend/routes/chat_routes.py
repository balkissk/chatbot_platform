import json
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chat_schema import ChatRequest, ChatSessionCreate
from models.chatbot import Chatbot
from models.chatbot_schema import chatbot_language_instruction, safe_chatbot_language
from models.conversation import ConversationMessage, ConversationSession
from models.llm_config import LLMConfig
from models.version import VersionChatbot
from services.ai_provider import AIProviderError, configured_chat_model, generate_chat_completion, stream_chat_completion
from services.auth import get_current_user
from services.flow_runtime import execute_flow
from services.rag import retrieve_relevant_chunks_with_mode
from services.rag_settings import normalize_rag_settings
from services.templates import localize_text

router = APIRouter()


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


RAG_CONTEXT_CHARS_PER_CHUNK = int_env("RAG_CONTEXT_CHARS_PER_CHUNK", 1400)
CHAT_HISTORY_MESSAGES = max(0, min(int_env("CHAT_HISTORY_MESSAGES", 6), 20))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_chatbot(db: Session, chatbot_id: int) -> Chatbot:
    chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")
    if not chatbot.is_active:
        raise HTTPException(status_code=403, detail="Chatbot is disabled")
    return chatbot


def get_chat_version(db: Session, chatbot_id: int, version_id: int | None, current_user) -> VersionChatbot:
    if version_id is not None:
        if current_user.role not in {"admin", "manager"}:
            raise HTTPException(status_code=403, detail="Version preview is not allowed")
        version = db.query(VersionChatbot).filter(
            VersionChatbot.id == version_id,
            VersionChatbot.chatbot_id == chatbot_id
        ).first()
    else:
        chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
        version = None
        if chatbot and chatbot.active_version_id:
            version = db.query(VersionChatbot).filter(
                VersionChatbot.id == chatbot.active_version_id,
                VersionChatbot.chatbot_id == chatbot_id
            ).first()
        if not version:
            version = db.query(VersionChatbot).filter(
                VersionChatbot.chatbot_id == chatbot_id,
                VersionChatbot.status == "published"
            ).first()

    if not version:
        raise HTTPException(status_code=404, detail="No version available")

    return version


def create_session(db: Session, chatbot_id: int, version_id: int, user_id: int | None, language: str | None = None) -> ConversationSession:
    session = ConversationSession(
        chatbot_id=chatbot_id,
        version_id=version_id,
        user_id=user_id,
        current_node_key=None,
        variables={"__language": safe_chatbot_language(language)}
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_or_create_session(
    db: Session,
    payload: ChatRequest,
    version: VersionChatbot,
    current_user,
    language: str | None = None
) -> ConversationSession:
    if payload.session_id is None:
        return create_session(db, payload.chatbot_id, version.id, current_user.id, language)

    session = db.query(ConversationSession).filter(
        ConversationSession.id == payload.session_id,
        ConversationSession.chatbot_id == payload.chatbot_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    if session.user_id and session.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Conversation session is not accessible")

    variables = session.variables or {}
    normalized_language = safe_chatbot_language(language)
    if variables.get("__language") != normalized_language:
        variables["__language"] = normalized_language
        session.variables = variables
        db.commit()

    return session


def session_history(
    db: Session,
    session_id: int,
    limit: int | None = None,
    exclude_latest_user_message: str | None = None,
) -> list[ConversationMessage]:
    limit = CHAT_HISTORY_MESSAGES if limit is None else max(0, min(int(limit), 20))
    if limit <= 0:
        return []
    rows = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session_id
    ).order_by(ConversationMessage.id.desc()).limit(limit + 1).all()
    history = list(reversed(rows))
    if exclude_latest_user_message and history:
        latest = history[-1]
        if latest.role == "user" and latest.content.strip() == exclude_latest_user_message.strip():
            history = history[:-1]
    return history[-limit:]


def format_history(messages: list[ConversationMessage]) -> str:
    if not messages:
        return "No previous conversation."

    return "\n".join(
        f"{message.role}: {message.content}"
        for message in messages
    )


def elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def estimated_token_count(text: str) -> int:
    # tiktoken is not a project dependency; this is a safe rough estimate for diagnostics only.
    return max(0, round(len(text or "") / 4))


def compact_context_text(text: str) -> str:
    value = (text or "").strip()
    limit = max(400, min(RAG_CONTEXT_CHARS_PER_CHUNK, 3000))
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n[Context truncated for latency]"


def unique_prompt_lines(lines: list[str]) -> list[str]:
    seen = set()
    result = []
    for line in lines:
        normalized = " ".join((line or "").strip().split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def prompt_variables(variables: dict) -> dict:
    excluded = {
        "__knowledge_search_sources",
        "__last_api_response",
    }
    return {
        key: value
        for key, value in (variables or {}).items()
        if key not in excluded and not key.endswith("_sources")
    }


def add_message(
    db: Session,
    session_id: int,
    role: str,
    content: str,
    options: list[str] | None = None,
    sources: list[dict] | None = None
) -> None:
    if not content:
        return

    db.add(ConversationMessage(
        session_id=session_id,
        role=role,
        content=content,
        options=options,
        sources=sources
    ))


def response_profile_for(length: str) -> dict:
    profiles = {
        "short": {
            "instruction": "Keep the answer short: 1 to 3 concise sentences. Do not add lists unless the user asks.",
            "num_predict": 80
        },
        "normal": {
            "instruction": "Answer in 3 to 6 clear sentences. Use bullets only when they make the answer easier to scan.",
            "num_predict": 140
        },
        "detailed": {
            "instruction": "Give a complete answer with useful details, but stay focused on the question.",
            "num_predict": 240
        }
    }
    return profiles.get(length, profiles["short"])


def _bool_setting(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _response_length(value: str | None, default: str) -> str:
    mapping = {
        "short": "short",
        "medium": "normal",
        "normal": "normal",
        "long": "detailed",
        "detailed": "detailed"
    }
    return mapping.get((value or "").strip().lower(), default)


def merge_node_rag_settings(rag_settings: dict, node_config: dict | None) -> dict:
    settings = {**rag_settings}
    if not node_config:
        return settings

    if "use_knowledge_base" in node_config:
        settings["use_knowledge_base"] = _bool_setting(node_config.get("use_knowledge_base"), True)
    else:
        settings["use_knowledge_base"] = True

    if not settings["use_knowledge_base"]:
        settings["strict_context"] = False
        settings["show_sources"] = False

    if "answer_only_from_documents" in node_config:
        settings["strict_context"] = _bool_setting(node_config.get("answer_only_from_documents"), settings["strict_context"])
    if "strict_context" in node_config:
        settings["strict_context"] = _bool_setting(node_config.get("strict_context"), settings["strict_context"])
    if not settings["use_knowledge_base"]:
        settings["strict_context"] = False
    if "show_sources" in node_config:
        node_show_sources = _bool_setting(node_config.get("show_sources"), settings["show_sources"])
        settings["show_sources"] = bool(settings["show_sources"] and node_show_sources)
    if "response_length" in node_config:
        settings["response_length"] = _response_length(node_config.get("response_length"), settings["response_length"])

    settings["fallback"] = str(node_config.get("fallback") or "").strip()
    settings["instructions"] = str(
        node_config.get("prompt")
        or node_config.get("instructions")
        or ""
    ).strip()
    return settings


def prepare_rag_generation(
    db: Session,
    version: VersionChatbot,
    config: LLMConfig,
    message: str,
    variables: dict | None = None,
    history: list[ConversationMessage] | None = None,
    mode_used: str = "flow_rag",
    node_config: dict | None = None
) -> dict:
    prompt_started_at = time.perf_counter()
    db_started_at = time.perf_counter()
    chatbot = db.query(Chatbot).filter(Chatbot.id == version.chatbot_id).first()
    prompt_db_query_ms = elapsed_ms(db_started_at)
    rag_settings = merge_node_rag_settings(
        normalize_rag_settings(chatbot.rag_settings if chatbot else None),
        node_config
    )
    retrieval_started_at = time.perf_counter()
    if rag_settings.get("use_knowledge_base", True):
        retrieval = retrieve_relevant_chunks_with_mode(
            db=db,
            version_id=version.id,
            query=message,
            limit=rag_settings["max_chunks"],
            retrieval_mode=rag_settings["retrieval_mode"],
            min_score=rag_settings["min_score"]
        )
    else:
        retrieval = {"mode": "ai_only", "chunks": []}
    retrieval_ms = elapsed_ms(retrieval_started_at)
    retrieved_chunks = retrieval["chunks"]

    context_blocks = []
    for index, (chunk, document, score) in enumerate(retrieved_chunks, start=1):
        context_blocks.append(
            f"[Source {index}: {document.filename}, score={score:.2f}]\n{compact_context_text(chunk.text)}"
        )

    context = "\n\n".join(context_blocks)
    system_prompt = config.system_prompt or "You are a helpful assistant"
    language_instruction = chatbot_language_instruction(chatbot.language if chatbot else None)
    vars_value = variables or {}
    history_text = format_history(history or [])
    variables_for_prompt = prompt_variables(vars_value)
    variables_text = str(variables_for_prompt)
    previous_answer = vars_value.get("__last_ai_answer", "")
    feedback = vars_value.get("__feedback", "")
    missing_context_instruction = (
        "If the knowledge context does not contain the answer, say that the available knowledge base does not contain enough information."
        if rag_settings["strict_context"]
        else "If the knowledge context is weak or missing, answer from general knowledge and clearly say that the answer is not confirmed by the uploaded documents."
    )
    response_profile = response_profile_for(rag_settings["response_length"])
    instructions = unique_prompt_lines([
        system_prompt,
        language_instruction,
        "Use the knowledge context to answer the user directly.",
        rag_settings.get("instructions") or "",
        response_profile["instruction"],
        "Use the conversation history and variables only as background context.",
        "Do not describe what you would do.",
        'Do not mention "the user expressed", "previous answer", "feedback", or "knowledge base" unless the user asks about that.',
        "If feedback is not_helpful, silently retry the original question with a clearer, more useful answer.",
        missing_context_instruction,
    ])
    prompt = "\n".join(instructions) + f"""

Conversation history:
{history_text}

Variables:
{variables_text}

Previous AI answer:
{previous_answer or "None"}

Feedback:
{feedback or "none"}

Knowledge context:
{context or "No relevant context was found."}

User question:
{message}
"""
    prompt_build_ms = elapsed_ms(prompt_started_at)
    sources = [
        {
            "document_id": document.id,
            "filename": document.filename,
            "chunk_id": chunk.id,
            "title": chunk.title,
            "section_type": chunk.section_type,
            "score": score,
            "text": chunk.text
        }
        for chunk, document, score in retrieved_chunks
    ] if rag_settings["show_sources"] else []

    fallback_response = rag_settings.get("fallback") if not retrieved_chunks and rag_settings.get("strict_context") else ""
    if fallback_response and chatbot:
        fallback_response = localize_text(fallback_response, chatbot.language)

    return {
        "prompt": prompt,
        "options": {
            "temperature": config.temperature,
            "num_predict": response_profile["num_predict"]
        },
        "model": configured_chat_model(config.model),
        "model_used": configured_chat_model(config.model),
        "retrieval_mode": retrieval["mode"],
        "version_used": version.id,
        "variables": vars_value,
        "sources": sources,
        "mode_used": mode_used,
        "fallback_response": fallback_response,
        "metrics": {
            "retrieval_ms": retrieval_ms,
            "prompt_build_ms": prompt_build_ms,
            "prompt_db_query_ms": prompt_db_query_ms,
            "top_k": rag_settings["max_chunks"],
            "retrieved_chunks": len(retrieved_chunks),
            "context_chars": len(context),
            "system_prompt_tokens": estimated_token_count("\n".join(instructions)),
            "history_tokens": estimated_token_count(history_text),
            "rag_context_tokens": estimated_token_count(context),
            "variables_tokens": estimated_token_count(variables_text),
            "prompt_tokens_estimated": estimated_token_count(prompt),
        }
    }


def build_rag_response(
    db: Session,
    version: VersionChatbot,
    config: LLMConfig,
    message: str,
    variables: dict | None = None,
    history: list[ConversationMessage] | None = None,
    mode_used: str = "flow_rag",
    node_config: dict | None = None
) -> dict:
    generation = prepare_rag_generation(
        db=db,
        version=version,
        config=config,
        message=message,
        variables=variables,
        history=history,
        mode_used=mode_used,
        node_config=node_config
    )

    answer = generation.get("fallback_response") or ""
    if not answer:
        try:
            answer = generate_chat_completion(
                prompt=generation["prompt"],
                model=generation["model"],
                temperature=generation["options"]["temperature"],
                max_tokens=generation["options"]["num_predict"]
            )
        except AIProviderError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LLM service error: {exc}"
            )

    return {
        "response": answer,
        "messages": [{"text": answer, "options": []}],
        "mode_used": "fallback" if generation.get("fallback_response") else generation["mode_used"],
        "retrieval_mode": generation["retrieval_mode"],
        "model_used": generation["model_used"],
        "version_used": generation["version_used"],
        "current_node_key": None,
        "variables": generation["variables"],
        "options": [],
        "sources": generation["sources"],
        "latency": generation.get("metrics") or {}
    }


def stream_event(event_type: str, payload: dict) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def sse_event(event_type: str, payload: dict) -> str:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps({'type': event_type, **payload}, ensure_ascii=False)}\n\n"
    )


def stream_ai_answer(generation: dict):
    answer_parts = []
    llm_metrics = generation.setdefault("llm_metrics", {})
    try:
        for token in stream_chat_completion(
            prompt=generation["prompt"],
            model=generation["model"],
            temperature=generation["options"]["temperature"],
            max_tokens=generation["options"]["num_predict"],
            metrics=llm_metrics,
        ):
            answer_parts.append(token)
            yield token
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}")

    generation["answer"] = "".join(answer_parts)


@router.post("/chat/sessions")
def start_chat_session(
    data: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    chatbot = get_chatbot(db, data.chatbot_id)
    version = get_chat_version(db, data.chatbot_id, data.version_id, current_user)
    session = create_session(db, data.chatbot_id, version.id, current_user.id, chatbot.language)

    return {
        "session_id": session.id,
        "chatbot_id": session.chatbot_id,
        "version_id": session.version_id,
        "current_node_key": session.current_node_key,
        "variables": session.variables or {}
    }


@router.post("/chat")
def chat(
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    chatbot = get_chatbot(db, data.chatbot_id)
    version = get_chat_version(db, data.chatbot_id, data.version_id, current_user)
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()

    if not config:
        raise HTTPException(status_code=404, detail="No config")

    session = get_or_create_session(db, data, version, current_user, chatbot.language)
    history = session_history(db, session.id)
    variables = {**(data.variables or {}), **(session.variables or {}), "__language": safe_chatbot_language(chatbot.language)}

    if data.message.strip():
        add_message(db, session.id, "user", data.message.strip())
        db.commit()

    def rag_answer(message: str, fallback_variables: dict | None = None, node_config: dict | None = None):
        return build_rag_response(
            db,
            version,
            config,
            message,
            fallback_variables or variables,
            history=session_history(db, session.id, exclude_latest_user_message=message),
            mode_used="flow_rag",
            node_config=node_config
        )

    result = execute_flow(
        db=db,
        version_id=version.id,
        message=data.message,
        current_node_key=session.current_node_key,
        variables=variables,
        rag_answer=rag_answer,
        allow_rag_fallback=False
    )

    session.current_node_key = result.get("current_node_key")
    session.variables = result.get("variables") or {}

    bot_messages = result.get("messages") or [
        {"text": result.get("response", ""), "options": result.get("options", [])}
    ]
    for item in bot_messages:
        add_message(
            db,
            session.id,
            "bot",
            item.get("text", ""),
            options=item.get("options") or [],
            sources=result.get("sources") or []
        )

    db.commit()

    return {
        **result,
        "session_id": session.id,
        "current_node_key": session.current_node_key,
        "variables": session.variables or {}
    }


@router.post("/chat/stream")
def chat_stream(
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    request_started_at = time.perf_counter()
    backend_received_epoch_ms = round(time.time() * 1000)
    latency_trace: dict = {
        "backend_entry_ms": 0,
        "backend_received_epoch_ms": backend_received_epoch_ms,
        "client_send_to_backend_received_ms": (
            round(backend_received_epoch_ms - data.client_send_at_ms)
            if data.client_send_at_ms else None
        ),
        "client_dispatch_to_backend_received_ms": (
            round(backend_received_epoch_ms - data.client_request_dispatched_at_ms)
            if data.client_request_dispatched_at_ms else None
        ),
        "db_query_ms": 0,
    }
    db_started_at = time.perf_counter()
    chatbot = get_chatbot(db, data.chatbot_id)
    latency_trace["db_query_ms"] += elapsed_ms(db_started_at)
    db_started_at = time.perf_counter()
    version = get_chat_version(db, data.chatbot_id, data.version_id, current_user)
    latency_trace["db_query_ms"] += elapsed_ms(db_started_at)
    db_started_at = time.perf_counter()
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    latency_trace["db_query_ms"] += elapsed_ms(db_started_at)

    if not config:
        raise HTTPException(status_code=404, detail="No config")

    db_started_at = time.perf_counter()
    session = get_or_create_session(db, data, version, current_user, chatbot.language)
    latency_trace["db_query_ms"] += elapsed_ms(db_started_at)
    variables = {**(data.variables or {}), **(session.variables or {}), "__language": safe_chatbot_language(chatbot.language)}

    user_message = data.message.strip()

    generation_holder: dict = {}
    flow_trace: dict = {}

    def rag_answer(message: str, fallback_variables: dict | None = None, node_config: dict | None = None):
        generation_holder["generation"] = prepare_rag_generation(
            db=db,
            version=version,
            config=config,
            message=message,
            variables=fallback_variables or variables,
            history=session_history(db, session.id, exclude_latest_user_message=message),
            mode_used="flow_rag",
            node_config=node_config
        )
        return {
            "response": generation_holder["generation"].get("fallback_response") or "",
            "messages": [{"text": generation_holder["generation"].get("fallback_response") or "", "options": []}],
            "mode_used": "fallback" if generation_holder["generation"].get("fallback_response") else "flow_rag",
            "retrieval_mode": generation_holder["generation"]["retrieval_mode"],
            "model_used": generation_holder["generation"]["model_used"],
            "version_used": version.id,
            "current_node_key": None,
            "variables": fallback_variables or variables,
            "options": [],
            "sources": generation_holder["generation"]["sources"]
        }

    flow_started_at = time.perf_counter()
    result = execute_flow(
        db=db,
        version_id=version.id,
        message=data.message,
        current_node_key=session.current_node_key,
        variables=variables,
        rag_answer=rag_answer,
        allow_rag_fallback=False,
        trace=flow_trace,
    )
    latency_trace["flow_execution_ms"] = elapsed_ms(flow_started_at)
    latency_trace["db_query_ms"] += int(flow_trace.get("flow_db_query_ms", 0) or 0)

    def event_generator():
        yield sse_event("start", {
            "session_id": session.id,
            "current_node_key": result.get("current_node_key"),
            "variables": result.get("variables") or {},
            "latency": {**latency_trace, "total_ms": elapsed_ms(request_started_at)}
        })

        generation = generation_holder.get("generation")
        if not generation:
            session.current_node_key = result.get("current_node_key")
            session.variables = result.get("variables") or {}
            bot_messages = result.get("messages") or [
                {"text": result.get("response", ""), "options": result.get("options", [])}
            ]
            if user_message:
                add_message(db, session.id, "user", user_message)
            for item in bot_messages:
                add_message(
                    db,
                    session.id,
                    "bot",
                    item.get("text", ""),
                    options=item.get("options") or [],
                    sources=result.get("sources") or []
                )
            db_started_at = time.perf_counter()
            db.commit()
            latency_trace["db_query_ms"] += elapsed_ms(db_started_at)
            yield sse_event("final", {
                **result,
                "session_id": session.id,
                "current_node_key": session.current_node_key,
                "variables": session.variables or {},
                "latency": {
                    **latency_trace,
                    "flow_db_query_ms": flow_trace.get("flow_db_query_ms", 0),
                    "flow_invocations": flow_trace.get("flow_invocations", 0),
                    "total_ms": elapsed_ms(request_started_at),
                }
            })
            return

        if generation.get("fallback_response"):
            final_result = {
                **result,
                "response": generation["fallback_response"],
                "messages": [{"text": generation["fallback_response"], "options": []}],
                "mode_used": "fallback",
                "retrieval_mode": generation["retrieval_mode"],
                "model_used": generation["model_used"],
                "version_used": generation["version_used"],
                "sources": []
            }
            session.current_node_key = final_result.get("current_node_key")
            session.variables = final_result.get("variables") or {}
            if user_message:
                add_message(db, session.id, "user", user_message)
            add_message(db, session.id, "bot", generation["fallback_response"], sources=[])
            db_started_at = time.perf_counter()
            db.commit()
            latency_trace["db_query_ms"] += elapsed_ms(db_started_at)
            yield sse_event("final", {
                **final_result,
                "session_id": session.id,
                "current_node_key": session.current_node_key,
                "variables": session.variables or {},
                "latency": {
                    **latency_trace,
                    **(generation.get("metrics") or {}),
                    "first_token_ms": 0,
                    "llm_ms": 0,
                    "flow_db_query_ms": flow_trace.get("flow_db_query_ms", 0),
                    "flow_invocations": flow_trace.get("flow_invocations", 0),
                    "total_ms": elapsed_ms(request_started_at)
                }
            })
            return

        llm_started_at = time.perf_counter()
        first_token_ms = None
        first_sse_sent_ms = None
        first_sse_forwarding_delay_ms = None
        try:
            for token in stream_ai_answer(generation):
                if first_token_ms is None:
                    first_token_ms = elapsed_ms(request_started_at)
                    first_sse_sent_ms = elapsed_ms(request_started_at)
                    azure_first_chunk_epoch_ms = generation.get("llm_metrics", {}).get("azure_first_chunk_epoch_ms")
                    if isinstance(azure_first_chunk_epoch_ms, int):
                        first_sse_forwarding_delay_ms = max(0, round(time.time() * 1000) - azure_first_chunk_epoch_ms)
                yield sse_event("token", {
                    "text": token,
                    "latency": {
                        "first_sse_sent_ms": first_sse_sent_ms,
                        "first_sse_forwarding_delay_ms": first_sse_forwarding_delay_ms,
                    } if first_sse_sent_ms is not None else {}
                })
        except HTTPException as exc:
            if user_message:
                add_message(db, session.id, "user", user_message)
                db_started_at = time.perf_counter()
                db.commit()
                latency_trace["db_query_ms"] += elapsed_ms(db_started_at)
            yield sse_event("error", {
                "detail": exc.detail,
                "latency": {
                    **latency_trace,
                    **(generation.get("metrics") or {}),
                    **(generation.get("llm_metrics") or {}),
                    "first_token_ms": first_token_ms,
                    "first_sse_sent_ms": first_sse_sent_ms,
                    "first_sse_forwarding_delay_ms": first_sse_forwarding_delay_ms,
                    "llm_ms": elapsed_ms(llm_started_at),
                    "flow_db_query_ms": flow_trace.get("flow_db_query_ms", 0),
                    "flow_invocations": flow_trace.get("flow_invocations", 0),
                    "total_ms": elapsed_ms(request_started_at),
                }
            })
            return
        llm_ms = elapsed_ms(llm_started_at)

        answer = generation.get("answer", "")
        messages = result.get("messages") or [{"text": "", "options": result.get("options", [])}]
        if messages:
            messages[0] = {**messages[0], "text": answer}

        final_result = {
            **result,
            "response": answer,
            "messages": messages,
            "mode_used": generation["mode_used"],
            "retrieval_mode": generation["retrieval_mode"],
            "model_used": generation["model_used"],
            "version_used": generation["version_used"],
            "sources": generation["sources"]
        }
        final_variables = final_result.get("variables") or {}
        final_variables["__last_ai_answer"] = answer
        final_result["variables"] = final_variables

        session.current_node_key = final_result.get("current_node_key")
        session.variables = final_variables
        if user_message:
            add_message(db, session.id, "user", user_message)
        for item in final_result.get("messages") or []:
            add_message(
                db,
                session.id,
                "bot",
                item.get("text", ""),
                options=item.get("options") or [],
                sources=final_result.get("sources") or []
            )
        db_started_at = time.perf_counter()
        db.commit()
        latency_trace["db_query_ms"] += elapsed_ms(db_started_at)

        yield sse_event("final", {
            **final_result,
            "session_id": session.id,
            "current_node_key": session.current_node_key,
            "variables": session.variables or {},
            "latency": {
                **latency_trace,
                **(generation.get("metrics") or {}),
                **(generation.get("llm_metrics") or {}),
                "first_token_ms": first_token_ms,
                "first_sse_sent_ms": first_sse_sent_ms,
                "first_sse_forwarding_delay_ms": first_sse_forwarding_delay_ms,
                "llm_ms": llm_ms,
                "flow_db_query_ms": flow_trace.get("flow_db_query_ms", 0),
                "flow_invocations": flow_trace.get("flow_invocations", 0),
                "total_ms": elapsed_ms(request_started_at)
            }
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
