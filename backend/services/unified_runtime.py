import logging
import re
import time
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.chatbot import Chatbot
from models.chatbot_schema import safe_chatbot_language
from models.conversation import ConversationSession
from models.llm_config import LLMConfig
from models.runtime_log import RuntimeLog
from models.version import VersionChatbot
from routes.chat_routes import add_message, build_rag_response, session_history
from services.flow_runtime import execute_flow

logger = logging.getLogger(__name__)

SENSITIVE_PATTERNS = [
    re.compile(r"(api[_-]?key|access[_-]?token|password|secret|authorization)\s*[:=]\s*[^,\s]+", re.I),
    re.compile(r"(postgresql|postgres|mysql|mssql|sqlite)://[^\s]+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+", re.I),
]


def runtime_response_time_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def runtime_error_type(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = str(exc.detail or "")
        if "published version" in detail.lower():
            return "PublishedVersionNotFound"
        if "configuration" in detail.lower():
            return "RuntimeConfigurationError"
        if "not available" in detail.lower():
            return "ChatbotUnavailable"
    return exc.__class__.__name__ or "InternalRuntimeError"


def sanitize_error_message(exc: Exception, max_length: int = 500) -> str:
    message = str(getattr(exc, "detail", None) or exc)
    for pattern in SENSITIVE_PATTERNS:
        message = pattern.sub("[redacted]", message)
    return message[:max_length]


def runtime_rag_used(result: dict | None) -> bool:
    if not result:
        return False
    retrieval_mode = str(result.get("retrieval_mode") or "").strip().lower()
    if retrieval_mode and retrieval_mode not in {"none", "ai_only"}:
        return True
    return bool(result.get("sources"))


def persist_runtime_log(
    db: Session,
    *,
    chatbot: Chatbot | None = None,
    version: VersionChatbot | None = None,
    session: ConversationSession | None = None,
    channel: str = "unknown",
    status: str,
    rag_used: bool = False,
    response_time_ms: int | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    source: str | None = None,
) -> None:
    try:
        log = RuntimeLog(
            chatbot_id=chatbot.id if chatbot else None,
            version_id=version.id if version else None,
            conversation_id=session.id if session else None,
            project_id=chatbot.project_id if chatbot else None,
            user_id=session.user_id if session else None,
            channel=channel or "unknown",
            status=status,
            rag_used=rag_used,
            response_time_ms=response_time_ms,
            error_type=error_type,
            error_message=error_message,
            source=source,
            completed_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist runtime log")


def get_active_version(db: Session, chatbot: Chatbot) -> VersionChatbot:
    logger.info(
        "Unified runtime selecting version: chatbot_id=%s active_version_id=%s",
        chatbot.id,
        chatbot.active_version_id,
    )
    print("Unified runtime chatbot_id =", chatbot.id)
    print("Unified runtime active_version_id =", chatbot.active_version_id)
    version = None
    if chatbot.active_version_id:
        version = db.query(VersionChatbot).filter(
            VersionChatbot.id == chatbot.active_version_id,
            VersionChatbot.chatbot_id == chatbot.id,
            VersionChatbot.status == "published"
        ).first()

    if not version:
        version = db.query(VersionChatbot).filter(
            VersionChatbot.chatbot_id == chatbot.id,
            VersionChatbot.status == "published"
        ).order_by(VersionChatbot.version_number.desc()).first()

    if not version:
        published_versions = db.query(VersionChatbot).filter(
            VersionChatbot.chatbot_id == chatbot.id
        ).all()
        print("Unified runtime published lookup failed. Versions =", [
            {"id": item.id, "status": item.status, "version_number": item.version_number}
            for item in published_versions
        ])
        raise HTTPException(status_code=404, detail="Chatbot has no published version")

    logger.info(
        "Unified runtime selected version: chatbot_id=%s version_id=%s status=%s",
        chatbot.id,
        version.id,
        version.status,
    )
    print("Unified runtime selected version id =", version.id)
    print("Unified runtime selected version status =", version.status)
    return version


def create_channel_session(
    db: Session,
    chatbot_id: int,
    version_id: int,
    channel: str,
    external_user_id: str | None = None,
    language: str | None = None,
) -> ConversationSession:
    session = ConversationSession(
        chatbot_id=chatbot_id,
        version_id=version_id,
        user_id=None,
        current_node_key=None,
        variables={
            "__channel": channel,
            "__external_user_id": external_user_id or "",
            "__language": safe_chatbot_language(language),
        }
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_or_create_channel_session(
    db: Session,
    chatbot_id: int,
    version_id: int,
    channel: str,
    external_user_id: str | None = None,
    session_id: int | str | None = None,
    language: str | None = None,
) -> ConversationSession:
    if isinstance(session_id, int):
        session = db.query(ConversationSession).filter(
            ConversationSession.id == session_id,
            ConversationSession.chatbot_id == chatbot_id,
            ConversationSession.user_id.is_(None),
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        if session.version_id != version_id:
            return create_channel_session(db, chatbot_id, version_id, channel, external_user_id, language)
        variables = session.variables or {}
        normalized_language = safe_chatbot_language(language)
        if variables.get("__language") != normalized_language:
            variables["__language"] = normalized_language
            session.variables = variables
            db.commit()
        return session

    if external_user_id:
        sessions = db.query(ConversationSession).filter(
            ConversationSession.chatbot_id == chatbot_id,
            ConversationSession.version_id == version_id,
            ConversationSession.user_id.is_(None),
        ).order_by(ConversationSession.updated_at.desc()).limit(100).all()
        for session in sessions:
            variables = session.variables or {}
            if variables.get("__channel") == channel and variables.get("__external_user_id") == external_user_id:
                normalized_language = safe_chatbot_language(language)
                if variables.get("__language") != normalized_language:
                    variables["__language"] = normalized_language
                    session.variables = variables
                    db.commit()
                return session

    return create_channel_session(db, chatbot_id, version_id, channel, external_user_id, language)


def run_chatbot_message(
    db: Session,
    chatbot_id: int,
    channel: str,
    external_user_id: str | None,
    message: str,
    session_id: int | str | None = None,
) -> dict:
    started_at = time.perf_counter()
    chatbot = None
    version = None
    session = None
    rag_used = False
    try:
        chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
        if not chatbot or not chatbot.is_active:
            raise HTTPException(status_code=404, detail="Chatbot is not available")

        version = get_active_version(db, chatbot)
        config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
        if not config:
            raise HTTPException(status_code=404, detail="Chatbot configuration is missing")

        session = get_or_create_channel_session(
            db=db,
            chatbot_id=chatbot.id,
            version_id=version.id,
            channel=channel,
            external_user_id=external_user_id,
            session_id=session_id,
            language=chatbot.language,
        )
        variables = {
            **(session.variables or {}),
            "__channel": channel,
            "__external_user_id": external_user_id or "",
            "__external_session_id": str(session_id or ""),
            "__language": safe_chatbot_language(chatbot.language),
        }

        if message.strip():
            add_message(db, session.id, "user", message.strip())
            db.commit()

        def rag_answer(query: str, fallback_variables: dict | None = None, node_config: dict | None = None):
            nonlocal rag_used
            rag_result = build_rag_response(
                db=db,
                version=version,
                config=config,
                message=query,
                variables=fallback_variables or variables,
                history=session_history(db, session.id),
                mode_used=f"{channel}_flow_rag",
                node_config=node_config,
            )
            rag_used = rag_used or runtime_rag_used(rag_result)
            return rag_result

        result = execute_flow(
            db=db,
            version_id=version.id,
            message=message,
            current_node_key=session.current_node_key,
            variables=variables,
            rag_answer=rag_answer,
            allow_rag_fallback=False,
        )
        response_value = result.get("response") or " | ".join(
            str(item.get("text") or "")
            for item in result.get("messages") or []
            if str(item.get("text") or "")
        )
        logger.info("Unified runtime response text: chatbot_id=%s response=%s", chatbot_id, response_value)
        print("Unified runtime response text =", response_value)

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
                sources=result.get("sources") or [],
            )

        db.commit()
        response_time = runtime_response_time_ms(started_at)
        persist_runtime_log(
            db,
            chatbot=chatbot,
            version=version,
            session=session,
            channel=channel,
            status="success",
            rag_used=rag_used,
            response_time_ms=response_time,
            source="unified_runtime",
        )
        return {
            **result,
            "session_id": session.id,
            "current_node_key": session.current_node_key,
            "variables": session.variables or {},
        }
    except Exception as exc:
        db.rollback()
        persist_runtime_log(
            db,
            chatbot=chatbot,
            version=version,
            session=session,
            channel=channel,
            status="failed",
            rag_used=rag_used,
            response_time_ms=runtime_response_time_ms(started_at),
            error_type=runtime_error_type(exc),
            error_message=sanitize_error_message(exc),
            source="unified_runtime",
        )
        raise
