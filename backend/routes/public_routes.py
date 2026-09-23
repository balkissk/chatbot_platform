import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import load_environment
from database.db import SessionLocal
from models.chatbot import Chatbot
from models.chatbot_schema import safe_chatbot_language
from models.conversation import ConversationMessage, ConversationSession
from models.llm_config import LLMConfig
from models.version import VersionChatbot
from services.flow_runtime import execute_flow
from routes.chat_routes import add_message, build_rag_response, prepare_rag_generation, session_history, stream_ai_answer, stream_event
from services.unified_runtime import (
    persist_runtime_log,
    run_chatbot_message,
    runtime_error_type,
    runtime_response_time_ms,
    runtime_rag_used,
    sanitize_error_message,
)

router = APIRouter(prefix="/public")
load_environment()
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL") or os.getenv("API_BASE_URL") or ""


class PublicChatSessionCreate(BaseModel):
    chatbot_id: int


class PublicChatRequest(BaseModel):
    chatbot_id: int
    message: str
    session_id: int | None = None
    channel: str | None = None


class PublicFeedbackRequest(BaseModel):
    chatbot_id: int
    session_id: int
    rating: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_public_chatbot(db: Session, chatbot_id: int) -> Chatbot:
    chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
    if not chatbot or not chatbot.is_active:
        raise HTTPException(status_code=404, detail="Chatbot is not available")
    return chatbot


def get_api_chatbot(db: Session, chatbot_id: int, api_key: str | None) -> Chatbot:
    chatbot = get_public_chatbot(db, chatbot_id)
    if not chatbot.public_api_enabled:
        raise HTTPException(status_code=403, detail="Public API is disabled for this chatbot")
    if not chatbot.public_api_key or api_key != chatbot.public_api_key:
        raise HTTPException(status_code=401, detail="Invalid chatbot API key")
    return chatbot


def get_active_version(db: Session, chatbot: Chatbot) -> VersionChatbot:
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
        raise HTTPException(status_code=404, detail="Chatbot has no published version")

    return version


def request_channel(payload: PublicChatRequest | None) -> str:
    channel = str(getattr(payload, "channel", "") or "").strip().lower()
    return "widget" if channel == "widget" else "web"


def create_public_session(db: Session, chatbot_id: int, version_id: int, channel: str = "web", language: str | None = None) -> ConversationSession:
    session = ConversationSession(
        chatbot_id=chatbot_id,
        version_id=version_id,
        user_id=None,
        current_node_key=None,
        variables={"__channel": channel, "__language": safe_chatbot_language(language)}
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_or_create_public_session(
    db: Session,
    payload: PublicChatRequest,
    version: VersionChatbot
) -> ConversationSession:
    channel = request_channel(payload)
    if payload.session_id is None:
        chatbot = db.query(Chatbot).filter(Chatbot.id == payload.chatbot_id).first()
        return create_public_session(db, payload.chatbot_id, version.id, channel, chatbot.language if chatbot else None)

    session = db.query(ConversationSession).filter(
        ConversationSession.id == payload.session_id,
        ConversationSession.chatbot_id == payload.chatbot_id,
        ConversationSession.user_id.is_(None)
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    if session.version_id != version.id:
        chatbot = db.query(Chatbot).filter(Chatbot.id == payload.chatbot_id).first()
        return create_public_session(db, payload.chatbot_id, version.id, channel, chatbot.language if chatbot else None)

    variables = session.variables or {}
    if variables.get("__channel") != channel:
        variables["__channel"] = channel
    chatbot = db.query(Chatbot).filter(Chatbot.id == payload.chatbot_id).first()
    normalized_language = safe_chatbot_language(chatbot.language if chatbot else None)
    if variables.get("__language") != normalized_language:
        variables["__language"] = normalized_language
    session.variables = variables
    db.commit()

    return session


def public_chat_payload(result: dict, session_id: int | None = None) -> dict:
    messages = result.get("messages") or [
        {"text": result.get("response", ""), "options": result.get("options", [])}
    ]
    payload = {
        "session_id": session_id or result.get("session_id"),
        "response": result.get("response", ""),
        "messages": [
            {
                "text": item.get("text", ""),
                "options": item.get("options") or []
            }
            for item in messages
        ],
        "options": result.get("options") or []
    }
    sources = result.get("sources") or []
    if sources:
        payload["sources"] = [
            {
                "filename": source.get("filename"),
                "title": source.get("title")
            }
            for source in sources
        ]
    return payload


@router.get("/chatbots/{chatbot_id}")
def public_chatbot(chatbot_id: int, db: Session = Depends(get_db)):
    chatbot = get_public_chatbot(db, chatbot_id)
    version = get_active_version(db, chatbot)
    return {
        "id": chatbot.id,
        "name": chatbot.name,
        "description": chatbot.description,
        "language": safe_chatbot_language(chatbot.language),
        "channel": chatbot.channel,
        "active_version_id": version.id,
        "version_number": version.version_number
    }


@router.post("/chat/sessions")
def start_public_chat_session(
    data: PublicChatSessionCreate,
    db: Session = Depends(get_db)
):
    chatbot = get_public_chatbot(db, data.chatbot_id)
    version = get_active_version(db, chatbot)
    session = create_public_session(db, chatbot.id, version.id, language=chatbot.language)
    return {
        "session_id": session.id,
        "chatbot_id": session.chatbot_id,
        "version_id": session.version_id,
        "current_node_key": session.current_node_key,
        "variables": session.variables or {}
    }


@router.post("/chat")
def public_chat(data: PublicChatRequest, db: Session = Depends(get_db)):
    get_public_chatbot(db, data.chatbot_id)
    return public_chat_payload(run_chatbot_message(
        db=db,
        chatbot_id=data.chatbot_id,
        channel=request_channel(data),
        external_user_id=None,
        message=data.message,
        session_id=data.session_id,
    ))


@router.post("/chat/feedback")
def public_chat_feedback(data: PublicFeedbackRequest, db: Session = Depends(get_db)):
    get_public_chatbot(db, data.chatbot_id)
    session = db.query(ConversationSession).filter(
        ConversationSession.id == data.session_id,
        ConversationSession.chatbot_id == data.chatbot_id,
        ConversationSession.user_id.is_(None)
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    rating = data.rating.strip().lower()
    if rating not in {"helpful", "not_helpful"}:
        raise HTTPException(status_code=400, detail="Invalid feedback rating")

    variables = session.variables or {}
    variables["__feedback"] = rating
    variables["__feedback_at"] = datetime.utcnow().isoformat()
    session.variables = variables
    db.commit()
    return {"status": "saved", "rating": rating}


@router.post("/chat/stream")
def public_chat_stream(data: PublicChatRequest, db: Session = Depends(get_db)):
    started_at = time.perf_counter()
    channel = request_channel(data)
    chatbot = None
    version = None
    session = None
    rag_used = False
    try:
        chatbot = get_public_chatbot(db, data.chatbot_id)
        version = get_active_version(db, chatbot)
        config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
        if not config:
            raise HTTPException(status_code=404, detail="Chatbot configuration is missing")

        session = get_or_create_public_session(db, data, version)
        variables = {
            **(session.variables or {}),
            "__channel": channel,
            "__language": safe_chatbot_language(chatbot.language),
        }

        if data.message.strip():
            add_message(db, session.id, "user", data.message.strip())
            db.commit()

        generation_holder: dict = {}

        def rag_answer(message: str, fallback_variables: dict | None = None, node_config: dict | None = None):
            nonlocal rag_used
            generation_holder["generation"] = prepare_rag_generation(
                db=db,
                version=version,
                config=config,
                message=message,
                variables=fallback_variables or variables,
                history=session_history(db, session.id),
                mode_used="public_flow_rag",
                node_config=node_config
            )
            rag_result = {
                "response": generation_holder["generation"].get("fallback_response") or "",
                "messages": [{"text": generation_holder["generation"].get("fallback_response") or "", "options": []}],
                "mode_used": "fallback" if generation_holder["generation"].get("fallback_response") else "public_flow_rag",
                "retrieval_mode": generation_holder["generation"]["retrieval_mode"],
                "model_used": generation_holder["generation"]["model_used"],
                "version_used": version.id,
                "current_node_key": None,
                "variables": fallback_variables or variables,
                "options": [],
                "sources": generation_holder["generation"]["sources"]
            }
            rag_used = rag_used or runtime_rag_used(rag_result)
            return rag_result

        result = execute_flow(
            db=db,
            version_id=version.id,
            message=data.message,
            current_node_key=session.current_node_key,
            variables=variables,
            rag_answer=rag_answer,
            allow_rag_fallback=False
        )
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
            source="public_stream",
        )
        raise

    def event_generator():
        yield stream_event("start", {
            "session_id": session.id
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
            persist_runtime_log(
                db,
                chatbot=chatbot,
                version=version,
                session=session,
                channel=channel,
                status="success",
                rag_used=rag_used,
                response_time_ms=runtime_response_time_ms(started_at),
                source="public_stream",
            )
            yield stream_event("final", public_chat_payload({
                **result,
            }, session.id))
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
            persist_runtime_log(
                db,
                chatbot=chatbot,
                version=version,
                session=session,
                channel=channel,
                status="success",
                rag_used=rag_used,
                response_time_ms=runtime_response_time_ms(started_at),
                source="public_stream",
            )
            yield stream_event("final", public_chat_payload({
                **final_result,
            }, session.id))
            return

        try:
            for token in stream_ai_answer(generation):
                yield stream_event("token", {"text": token})
        except HTTPException as exc:
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
                source="public_stream",
            )
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
        persist_runtime_log(
            db,
            chatbot=chatbot,
            version=version,
            session=session,
            channel=channel,
            status="success",
            rag_used=rag_used,
            response_time_ms=runtime_response_time_ms(started_at),
            source="public_stream",
        )

        yield stream_event("final", public_chat_payload({
            **final_result,
        }, session.id))

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@router.post("/api/chat/sessions")
def start_public_api_chat_session(
    data: PublicChatSessionCreate,
    db: Session = Depends(get_db),
    x_chatbot_api_key: str | None = Header(default=None)
):
    chatbot = get_api_chatbot(db, data.chatbot_id, x_chatbot_api_key)
    version = get_active_version(db, chatbot)
    session = create_public_session(db, chatbot.id, version.id, language=chatbot.language)
    return {
        "session_id": session.id,
        "chatbot_id": session.chatbot_id,
        "version_id": session.version_id,
        "current_node_key": session.current_node_key,
        "variables": session.variables or {}
    }


@router.post("/api/chat")
def public_api_chat(
    data: PublicChatRequest,
    db: Session = Depends(get_db),
    x_chatbot_api_key: str | None = Header(default=None)
):
    get_api_chatbot(db, data.chatbot_id, x_chatbot_api_key)
    return run_chatbot_message(
        db=db,
        chatbot_id=data.chatbot_id,
        channel="api",
        external_user_id=None,
        message=data.message,
        session_id=data.session_id,
    )


@router.get("/widget.js")
def widget_script():
    default_api_base = PUBLIC_API_BASE_URL
    script = r"""
(function () {
  var currentScript = document.currentScript;
  var params = new URLSearchParams(window.location.search);
  var chatbotId = (currentScript && currentScript.getAttribute("data-chatbot-id")) || params.get("chatbotId");
  var apiBase = (currentScript && currentScript.getAttribute("data-api-base")) || "__DEFAULT_API_BASE__" || window.location.origin;
  var title = (currentScript && currentScript.getAttribute("data-title")) || "Chat";
  var sessionId = null;
  var isLoading = false;
  var hasStarted = false;

  if (!chatbotId) {
    console.error("Chatbot widget: data-chatbot-id is required.");
    return;
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  var style = document.createElement("style");
  style.textContent = "#cp-widget-button{position:fixed;right:22px;bottom:22px;z-index:2147483647;align-items:center;background:#12664f;border:0;border-radius:999px;box-shadow:0 14px 34px rgba(15,23,42,.24);box-sizing:border-box;color:#fff;cursor:pointer;display:inline-flex;font:700 14px Arial,sans-serif;gap:10px;justify-content:center;line-height:1;min-height:54px;padding:0 18px 0 16px;transition:background .16s ease,box-shadow .16s ease,transform .16s ease}.cp-widget-button-icon{display:block;flex:0 0 auto;height:22px;width:22px}.cp-widget-button-label{display:block}.cp-widget-button-icon path,.cp-widget-button-icon circle{stroke:currentColor}#cp-widget-button[hidden]{display:none!important}#cp-widget-button:hover{background:#0f5b47;box-shadow:0 16px 38px rgba(15,23,42,.28);transform:translateY(-1px)}#cp-widget-button:focus{outline:0}#cp-widget-button:focus-visible{box-shadow:0 0 0 3px rgba(18,102,79,.28),0 14px 34px rgba(15,23,42,.24)}#cp-widget-panel{position:fixed;right:22px;bottom:90px;z-index:2147483647;background:#fff;border:1px solid #d8e0ea;border-radius:16px;box-shadow:0 22px 60px rgba(15,23,42,.26);color:#17202a;display:none;font-family:Arial,sans-serif;height:min(620px,calc(100vh - 122px));box-sizing:border-box;overflow:hidden;width:min(390px,calc(100vw - 28px))}#cp-widget-panel.open{display:grid;grid-template-rows:auto minmax(0,1fr) auto}#cp-widget-header{align-items:center;box-sizing:border-box;width:100%;background:#12664f;color:#fff;display:flex;gap:12px;justify-content:space-between;padding:14px 16px}#cp-widget-title{display:grid;gap:2px;min-width:0}#cp-widget-title span{font-size:11px;letter-spacing:.08em;opacity:.78;text-transform:uppercase}#cp-widget-title strong{font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#cp-widget-close{align-items:center;background:rgba(255,255,255,.12);border:0;border-radius:999px;color:#fff;cursor:pointer;display:grid;font-size:21px;height:34px;line-height:1;place-items:center;width:34px}#cp-widget-close:hover,#cp-widget-close:focus{background:rgba(255,255,255,.22);outline:0}#cp-widget-messages{background:#f7f9fb;box-sizing:border-box;width:100%;display:flex;flex-direction:column;gap:10px;overflow:auto;padding:14px}.cp-msg{background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 8px 22px rgba(15,45,65,.05);box-sizing:border-box;color:#17202a;font-size:14px;line-height:1.45;max-width:82%;overflow-wrap:anywhere;padding:10px 12px;white-space:pre-wrap}.cp-msg.user{align-self:flex-end;background:#12664f;border-color:#12664f;color:#fff}.cp-msg.bot{align-self:flex-start}.cp-msg-text{display:block}.cp-options{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px}.cp-options button{background:#eef6f3;border:1px solid #b7dfd4;border-radius:999px;color:#0f5b47;cursor:pointer;font:700 13px Arial,sans-serif;padding:7px 10px}.cp-options button:disabled{cursor:not-allowed;opacity:.58}.cp-sources{border-top:1px solid #e7eef3;display:grid;gap:5px;margin-top:10px;padding-top:9px}.cp-sources-title{color:#52677a;font-size:12px;font-weight:700}.cp-source{color:#334155;font-size:12px;line-height:1.35}.cp-error{align-self:stretch;background:#fff5f5;border:1px solid #ffd6d6;border-radius:10px;color:#9f1239;font-size:13px;padding:9px 10px}.cp-typing{align-items:center;color:#52677a;display:inline-flex;gap:8px}.cp-typing-dots{display:inline-flex;gap:4px}.cp-typing-dots i{animation:cp-bounce .9s infinite ease-in-out;background:#12664f;border-radius:50%;display:block;height:7px;width:7px}.cp-typing-dots i:nth-child(2){animation-delay:.12s}.cp-typing-dots i:nth-child(3){animation-delay:.24s}@keyframes cp-bounce{0%,80%,100%{opacity:.42;transform:translateY(0)}40%{opacity:1;transform:translateY(-5px)}}.cp-composer{background:#fff;box-sizing:border-box;width:100%;border-top:1px solid #e2e8f0;display:grid;gap:8px;grid-template-columns:minmax(0,1fr) auto;padding:12px}.cp-composer input{border:1px solid #cbd5e1;border-radius:12px;box-sizing:border-box;font-size:14px;min-height:42px;min-width:0;padding:10px 12px}.cp-composer input:focus{border-color:#12664f;outline:0}.cp-composer button{background:#12664f;border:0;border-radius:12px;color:#fff;cursor:pointer;font-weight:700;min-height:42px;padding:0 14px}.cp-composer button:disabled{cursor:not-allowed;opacity:.62}@media (max-width:520px){#cp-widget-button{bottom:16px;right:16px;min-height:52px;padding:0 16px 0 15px}#cp-widget-panel{border-radius:16px 16px 0 0;bottom:0;height:min(720px,calc(100vh - 12px));left:0;right:0;width:100vw}.cp-msg{max-width:88%}}";
  document.head.appendChild(style);

  var panel = document.createElement("section");
  panel.id = "cp-widget-panel";
  panel.setAttribute("aria-label", title + " chat");
  panel.innerHTML = '<header id="cp-widget-header"><div id="cp-widget-title"><span>Assistant</span><strong>' + escapeHtml(title) + '</strong></div><button id="cp-widget-close" type="button" aria-label="Minimize chat">&times;</button></header><div id="cp-widget-messages" aria-live="polite"></div><form class="cp-composer"><input name="message" autocomplete="off" placeholder="Type your message" aria-label="Message"><button type="submit">Send</button></form>';
  var button = document.createElement("button");
  button.id = "cp-widget-button";
  button.type = "button";
  button.setAttribute("aria-label", "Open chat");
  button.innerHTML = '<svg class="cp-widget-button-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path><path d="M8 9h8"></path><path d="M8 13h5"></path></svg><span class="cp-widget-button-label">Chat</span>';

  document.body.appendChild(panel);
  document.body.appendChild(button);

  var messages = panel.querySelector("#cp-widget-messages");
  var form = panel.querySelector("form");
  var input = panel.querySelector("input");
  var sendButton = form.querySelector("button");
  var typingRow = null;

  function setLoading(value) {
    isLoading = value;
    input.disabled = value;
    sendButton.disabled = value || !input.value.trim();
    Array.prototype.forEach.call(panel.querySelectorAll(".cp-options button"), function (option) {
      option.disabled = value;
    });
  }

  function showTyping() {
    if (typingRow) return;
    typingRow = document.createElement("div");
    typingRow.className = "cp-msg bot cp-typing";
    typingRow.innerHTML = '<span class="cp-typing-dots"><i></i><i></i><i></i></span><span>Assistant is typing...</span>';
    messages.appendChild(typingRow);
    messages.scrollTop = messages.scrollHeight;
  }

  function hideTyping() {
    if (!typingRow) return;
    typingRow.remove();
    typingRow = null;
  }

  function sourceLabel(source) {
    return source.title || source.filename || "Reference";
  }

  function addSources(row, sources) {
    if (!sources || !sources.length) return;
    var refs = document.createElement("div");
    refs.className = "cp-sources";
    var title = document.createElement("div");
    title.className = "cp-sources-title";
    title.textContent = "Sources";
    refs.appendChild(title);
    sources.slice(0, 4).forEach(function (source) {
      var ref = document.createElement("div");
      ref.className = "cp-source";
      ref.textContent = sourceLabel(source);
      refs.appendChild(ref);
    });
    row.appendChild(refs);
  }

  function addOptions(row, options) {
    if (!options || !options.length) return;
    var opts = document.createElement("div");
    opts.className = "cp-options";
    options.forEach(function (option) {
      var opt = document.createElement("button");
      opt.type = "button";
      opt.textContent = option;
      opt.disabled = isLoading;
      opt.onclick = function () { send(option); };
      opts.appendChild(opt);
    });
    row.appendChild(opts);
  }

  function addMessage(role, text, options, sources) {
    hideTyping();
    var row = document.createElement("div");
    row.className = "cp-msg " + (role === "user" ? "user" : "bot");
    var body = document.createElement("span");
    body.className = "cp-msg-text";
    body.textContent = text || "";
    row.appendChild(body);
    addOptions(row, options);
    addSources(row, sources);
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
    return row;
  }

  function showError(text) {
    var row = document.createElement("div");
    row.className = "cp-error";
    row.textContent = text;
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
  }

  function responseMessages(response) {
    if (Array.isArray(response.messages) && response.messages.length) return response.messages;
    return [{ text: response.response || "", options: response.options || [] }];
  }

  function usableMessages(items) {
    return (items || []).filter(function (item) {
      return String(item && item.text || "").trim() || (item && item.options && item.options.length);
    });
  }

  function startConversation() {
    if (hasStarted || isLoading) return;
    hasStarted = true;
    requestRuntime("", false, true);
  }

  function send(text) {
    var value = (text || input.value || "").trim();
    if (!value || isLoading) return;
    requestRuntime(value, true, false);
  }

  function requestRuntime(value, showUserMessage, isInitialStart) {
    if (showUserMessage) {
      addMessage("user", value);
      input.value = "";
    }
    setLoading(true);
    showTyping();

    var streamRow = null;
    var streamedText = "";

    fetch(apiBase + "/public/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chatbot_id: Number(chatbotId), message: value, session_id: sessionId, channel: "widget" })
    }).then(function (res) {
      if (!res.ok || !res.body) return res.json().then(function (body) { throw new Error(body.detail || "Chat failed"); });
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";

      function handleEvent(event) {
        if (event.type === "start") {
          sessionId = event.session_id;
          return;
        }
        if (event.type === "token") {
          streamedText += event.text || "";
          if (!streamRow) {
            hideTyping();
            streamRow = addMessage("bot", streamedText);
          } else {
            var body = streamRow.querySelector(".cp-msg-text");
            if (body) body.textContent = streamedText;
            messages.scrollTop = messages.scrollHeight;
          }
          return;
        }
        if (event.type === "final") {
          sessionId = event.session_id;
          var items = usableMessages(responseMessages(event));
          if (!streamRow) {
            hideTyping();
            if (!items.length && isInitialStart) {
              addMessage("bot", "Hi, how can I help?");
              return;
            }
            items.forEach(function (item, index) {
              addMessage("bot", item.text, item.options || [], index === 0 ? event.sources : []);
            });
            return;
          }
          if (items[0]) {
            var textNode = streamRow.querySelector(".cp-msg-text");
            if (textNode) textNode.textContent = streamedText || items[0].text || "";
            addOptions(streamRow, items[0].options || []);
            addSources(streamRow, event.sources || []);
          }
          items.slice(1).forEach(function (item) { addMessage("bot", item.text, item.options || []); });
        }
        if (event.type === "error") {
          throw new Error(event.detail || "Chat failed");
        }
      }

      function read() {
        return reader.read().then(function (result) {
          if (result.done) {
            if (buffer.trim()) handleEvent(JSON.parse(buffer));
            return;
          }
          buffer += decoder.decode(result.value, { stream: true });
          var lines = buffer.split("\n");
          buffer = lines.pop() || "";
          lines.forEach(function (line) {
            if (line.trim()) handleEvent(JSON.parse(line));
          });
          return read();
        });
      }

      return read();
    }).catch(function (err) {
      if (isInitialStart) hasStarted = false;
      hideTyping();
      showError(err.message || "Chat failed");
    }).finally(function () {
      setLoading(false);
      input.focus();
    });
  }

  input.addEventListener("input", function () {
    sendButton.disabled = isLoading || !input.value.trim();
  });
  sendButton.disabled = true;
  button.onclick = function () {
    panel.classList.add("open");
    button.hidden = true;
    button.setAttribute("aria-label", "Chat is open");
    startConversation();
    setTimeout(function () { input.focus(); }, 0);
  };
  panel.querySelector("#cp-widget-close").onclick = function () {
    panel.classList.remove("open");
    button.hidden = false;
    button.setAttribute("aria-label", "Open chat");
    button.focus();
  };
  form.onsubmit = function (event) {
    event.preventDefault();
    send();
  };
})();
"""
    script = script.replace("__DEFAULT_API_BASE__", default_api_base)
    return Response(content=script, media_type="application/javascript")
