import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chat_schema import ChatRequest, ChatSessionCreate
from models.chatbot import Chatbot
from models.conversation import ConversationMessage, ConversationSession
from models.llm_config import LLMConfig
from models.version import VersionChatbot
from services.ai_provider import AIProviderError, configured_chat_model, generate_chat_completion, stream_chat_completion
from services.auth import get_current_user
from services.flow_runtime import execute_flow
from services.rag import retrieve_relevant_chunks_with_mode
from services.rag_settings import normalize_rag_settings

router = APIRouter()


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


def create_session(db: Session, chatbot_id: int, version_id: int, user_id: int | None) -> ConversationSession:
    session = ConversationSession(
        chatbot_id=chatbot_id,
        version_id=version_id,
        user_id=user_id,
        current_node_key=None,
        variables={}
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_or_create_session(
    db: Session,
    payload: ChatRequest,
    version: VersionChatbot,
    current_user
) -> ConversationSession:
    if payload.session_id is None:
        return create_session(db, payload.chatbot_id, version.id, current_user.id)

    session = db.query(ConversationSession).filter(
        ConversationSession.id == payload.session_id,
        ConversationSession.chatbot_id == payload.chatbot_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    if session.user_id and session.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Conversation session is not accessible")

    return session


def session_history(db: Session, session_id: int, limit: int = 8) -> list[ConversationMessage]:
    rows = db.query(ConversationMessage).filter(
        ConversationMessage.session_id == session_id
    ).order_by(ConversationMessage.id.desc()).limit(limit).all()
    return list(reversed(rows))


def format_history(messages: list[ConversationMessage]) -> str:
    if not messages:
        return "No previous conversation."

    return "\n".join(
        f"{message.role}: {message.content}"
        for message in messages
    )


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

    if "answer_only_from_documents" in node_config:
        settings["strict_context"] = _bool_setting(node_config.get("answer_only_from_documents"), settings["strict_context"])
    if "strict_context" in node_config:
        settings["strict_context"] = _bool_setting(node_config.get("strict_context"), settings["strict_context"])
    if "show_sources" in node_config:
        settings["show_sources"] = _bool_setting(node_config.get("show_sources"), settings["show_sources"])
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
    chatbot = db.query(Chatbot).filter(Chatbot.id == version.chatbot_id).first()
    rag_settings = merge_node_rag_settings(
        normalize_rag_settings(chatbot.rag_settings if chatbot else None),
        node_config
    )
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
    retrieved_chunks = retrieval["chunks"]

    context_blocks = []
    for index, (chunk, document, score) in enumerate(retrieved_chunks, start=1):
        context_blocks.append(
            f"[Source {index}: {document.filename}, score={score:.2f}]\n{chunk.text}"
        )

    context = "\n\n".join(context_blocks)
    system_prompt = config.system_prompt or "You are a helpful assistant"
    vars_value = variables or {}
    previous_answer = vars_value.get("__last_ai_answer", "")
    feedback = vars_value.get("__feedback", "")
    missing_context_instruction = (
        "If the knowledge context does not contain the answer, say that the available knowledge base does not contain enough information."
        if rag_settings["strict_context"]
        else "If the knowledge context is weak or missing, answer from general knowledge and clearly say that the answer is not confirmed by the uploaded documents."
    )
    response_profile = response_profile_for(rag_settings["response_length"])
    prompt = f"""
{system_prompt}

Use the knowledge context to answer the user directly.
{rag_settings.get("instructions") or ""}
{response_profile["instruction"]}
Use the conversation history and variables only as background context.
Do not describe what you would do. Do not mention "the user expressed", "previous answer", "feedback", or "knowledge base" unless the user asks about that.
If feedback is not_helpful, silently retry the original question with a clearer, more useful answer.
{missing_context_instruction}

Conversation history:
{format_history(history or [])}

Variables:
{vars_value}

Previous AI answer:
{previous_answer or "None"}

Feedback:
{feedback or "none"}

Knowledge context:
{context or "No relevant context was found."}

User question:
{message}
"""
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
        "fallback_response": rag_settings.get("fallback") if not retrieved_chunks and rag_settings.get("strict_context") else ""
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
        "sources": generation["sources"]
    }


def stream_event(event_type: str, payload: dict) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def stream_ai_answer(generation: dict):
    answer_parts = []
    try:
        for token in stream_chat_completion(
            prompt=generation["prompt"],
            model=generation["model"],
            temperature=generation["options"]["temperature"],
            max_tokens=generation["options"]["num_predict"]
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
    get_chatbot(db, data.chatbot_id)
    version = get_chat_version(db, data.chatbot_id, data.version_id, current_user)
    session = create_session(db, data.chatbot_id, version.id, current_user.id)

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
    get_chatbot(db, data.chatbot_id)
    version = get_chat_version(db, data.chatbot_id, data.version_id, current_user)
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()

    if not config:
        raise HTTPException(status_code=404, detail="No config")

    session = get_or_create_session(db, data, version, current_user)
    history = session_history(db, session.id)
    variables = session.variables or data.variables or {}

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
            history=session_history(db, session.id),
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
    get_chatbot(db, data.chatbot_id)
    version = get_chat_version(db, data.chatbot_id, data.version_id, current_user)
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()

    if not config:
        raise HTTPException(status_code=404, detail="No config")

    session = get_or_create_session(db, data, version, current_user)
    variables = session.variables or data.variables or {}

    if data.message.strip():
        add_message(db, session.id, "user", data.message.strip())
        db.commit()

    generation_holder: dict = {}

    def rag_answer(message: str, fallback_variables: dict | None = None, node_config: dict | None = None):
        generation_holder["generation"] = prepare_rag_generation(
            db=db,
            version=version,
            config=config,
            message=message,
            variables=fallback_variables or variables,
            history=session_history(db, session.id),
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

    result = execute_flow(
        db=db,
        version_id=version.id,
        message=data.message,
        current_node_key=session.current_node_key,
        variables=variables,
        rag_answer=rag_answer,
        allow_rag_fallback=False
    )

    def event_generator():
        yield stream_event("start", {
            "session_id": session.id,
            "current_node_key": result.get("current_node_key"),
            "variables": result.get("variables") or {}
        })

        generation = generation_holder.get("generation")
        if not generation:
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
            yield stream_event("final", {
                **result,
                "session_id": session.id,
                "current_node_key": session.current_node_key,
                "variables": session.variables or {}
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
            add_message(db, session.id, "bot", generation["fallback_response"], sources=[])
            db.commit()
            yield stream_event("final", {
                **final_result,
                "session_id": session.id,
                "current_node_key": session.current_node_key,
                "variables": session.variables or {}
            })
            return

        try:
            for token in stream_ai_answer(generation):
                yield stream_event("token", {"text": token})
        except HTTPException as exc:
            yield stream_event("error", {"detail": exc.detail})
            return

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
        for item in final_result.get("messages") or []:
            add_message(
                db,
                session.id,
                "bot",
                item.get("text", ""),
                options=item.get("options") or [],
                sources=final_result.get("sources") or []
            )
        db.commit()

        yield stream_event("final", {
            **final_result,
            "session_id": session.id,
            "current_node_key": session.current_node_key,
            "variables": session.variables or {}
        })

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
