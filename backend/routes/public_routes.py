import os

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot import Chatbot
from models.conversation import ConversationMessage, ConversationSession
from models.llm_config import LLMConfig
from models.version import VersionChatbot
from services.flow_runtime import execute_flow
from routes.chat_routes import add_message, build_rag_response, prepare_rag_generation, session_history, stream_event, stream_ollama_answer

router = APIRouter(prefix="/public")
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL") or os.getenv("API_BASE_URL") or ""


class PublicChatSessionCreate(BaseModel):
    chatbot_id: int


class PublicChatRequest(BaseModel):
    chatbot_id: int
    message: str
    session_id: int | None = None


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


def create_public_session(db: Session, chatbot_id: int, version_id: int) -> ConversationSession:
    session = ConversationSession(
        chatbot_id=chatbot_id,
        version_id=version_id,
        user_id=None,
        current_node_key=None,
        variables={}
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
    if payload.session_id is None:
        return create_public_session(db, payload.chatbot_id, version.id)

    session = db.query(ConversationSession).filter(
        ConversationSession.id == payload.session_id,
        ConversationSession.chatbot_id == payload.chatbot_id,
        ConversationSession.user_id.is_(None)
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    if session.version_id != version.id:
        return create_public_session(db, payload.chatbot_id, version.id)

    return session


def hide_public_sources(result: dict) -> dict:
    return {**result, "sources": []}


@router.get("/chatbots/{chatbot_id}")
def public_chatbot(chatbot_id: int, db: Session = Depends(get_db)):
    chatbot = get_public_chatbot(db, chatbot_id)
    version = get_active_version(db, chatbot)
    return {
        "id": chatbot.id,
        "name": chatbot.name,
        "description": chatbot.description,
        "language": chatbot.language,
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
    session = create_public_session(db, chatbot.id, version.id)
    return {
        "session_id": session.id,
        "chatbot_id": session.chatbot_id,
        "version_id": session.version_id,
        "current_node_key": session.current_node_key,
        "variables": session.variables or {}
    }


@router.post("/chat")
def public_chat(data: PublicChatRequest, db: Session = Depends(get_db)):
    chatbot = get_public_chatbot(db, data.chatbot_id)
    version = get_active_version(db, chatbot)
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Chatbot configuration is missing")

    session = get_or_create_public_session(db, data, version)
    variables = session.variables or {}

    if data.message.strip():
        add_message(db, session.id, "user", data.message.strip())
        db.commit()

    def rag_answer(message: str, fallback_variables: dict | None = None):
        return build_rag_response(
            db=db,
            version=version,
            config=config,
            message=message,
            variables=fallback_variables or variables,
            history=session_history(db, session.id),
            mode_used="public_flow_rag"
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

    return hide_public_sources({
        **result,
        "session_id": session.id,
        "current_node_key": session.current_node_key,
        "variables": session.variables or {}
    })


@router.post("/chat/stream")
def public_chat_stream(data: PublicChatRequest, db: Session = Depends(get_db)):
    chatbot = get_public_chatbot(db, data.chatbot_id)
    version = get_active_version(db, chatbot)
    config = db.query(LLMConfig).filter(LLMConfig.version_id == version.id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Chatbot configuration is missing")

    session = get_or_create_public_session(db, data, version)
    variables = session.variables or {}

    if data.message.strip():
        add_message(db, session.id, "user", data.message.strip())
        db.commit()

    generation_holder: dict = {}

    def rag_answer(message: str, fallback_variables: dict | None = None):
        generation_holder["generation"] = prepare_rag_generation(
            db=db,
            version=version,
            config=config,
            message=message,
            variables=fallback_variables or variables,
            history=session_history(db, session.id),
            mode_used="public_flow_rag"
        )
        return {
            "response": "",
            "messages": [{"text": "", "options": []}],
            "mode_used": "public_flow_rag",
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
            yield stream_event("final", hide_public_sources({
                **result,
                "session_id": session.id,
                "current_node_key": session.current_node_key,
                "variables": session.variables or {}
            }))
            return

        try:
            for token in stream_ollama_answer(generation):
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

        yield stream_event("final", hide_public_sources({
            **final_result,
            "session_id": session.id,
            "current_node_key": session.current_node_key,
            "variables": session.variables or {}
        }))

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@router.post("/api/chat/sessions")
def start_public_api_chat_session(
    data: PublicChatSessionCreate,
    db: Session = Depends(get_db),
    x_chatbot_api_key: str | None = Header(default=None)
):
    chatbot = get_api_chatbot(db, data.chatbot_id, x_chatbot_api_key)
    version = get_active_version(db, chatbot)
    session = create_public_session(db, chatbot.id, version.id)
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
    return public_chat(data, db)


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

  if (!chatbotId) {
    console.error("Chatbot widget: data-chatbot-id is required.");
    return;
  }

  var style = document.createElement("style");
  style.textContent = "#cp-widget-button{position:fixed;right:22px;bottom:22px;z-index:2147483647;border:0;border-radius:999px;background:#12664f;color:#fff;min-width:58px;height:58px;padding:0 18px;font:700 15px Arial;box-shadow:0 12px 30px rgba(0,0,0,.22);cursor:pointer}#cp-widget-panel{position:fixed;right:22px;bottom:92px;z-index:2147483647;width:min(370px,calc(100vw - 28px));height:min(560px,calc(100vh - 118px));background:#fff;border:1px solid #d8e0ea;border-radius:10px;box-shadow:0 18px 50px rgba(0,0,0,.24);display:none;overflow:hidden;font-family:Arial,sans-serif}#cp-widget-panel.open{display:grid;grid-template-rows:auto 1fr auto}#cp-widget-header{display:flex;align-items:center;justify-content:space-between;background:#12664f;color:#fff;padding:14px 16px}#cp-widget-header strong{font-size:15px}#cp-widget-close{background:transparent;border:0;color:#fff;font-size:22px;cursor:pointer}#cp-widget-messages{padding:14px;overflow:auto;background:#f7f9fb} .cp-msg{max-width:82%;margin:0 0 10px;padding:10px 12px;border-radius:10px;background:#fff;border:1px solid #e2e8f0;color:#17202a;font-size:14px;line-height:1.45}.cp-msg.user{margin-left:auto;background:#12664f;color:#fff;border-color:#12664f}.cp-options{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px}.cp-options button{border:1px solid #b7dfd4;background:#eef6f3;color:#0f766e;border-radius:999px;padding:7px 10px;cursor:pointer}.cp-error{color:#b00020;font-size:13px;margin:8px 0}.cp-composer{display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0}.cp-composer input{flex:1;border:1px solid #cbd5e1;border-radius:8px;padding:10px;font-size:14px}.cp-composer button{border:0;border-radius:8px;background:#12664f;color:#fff;font-weight:700;padding:0 14px;cursor:pointer}";
  document.head.appendChild(style);

  var panel = document.createElement("section");
  panel.id = "cp-widget-panel";
  panel.innerHTML = '<header id="cp-widget-header"><strong>' + title + '</strong><button id="cp-widget-close" type="button">×</button></header><div id="cp-widget-messages"><div class="cp-msg">Hi, how can I help?</div></div><form class="cp-composer"><input name="message" autocomplete="off" placeholder="Type your message"><button type="submit">Send</button></form>';

  var button = document.createElement("button");
  button.id = "cp-widget-button";
  button.type = "button";
  button.textContent = "Chat";

  document.body.appendChild(panel);
  document.body.appendChild(button);

  var messages = panel.querySelector("#cp-widget-messages");
  var form = panel.querySelector("form");
  var input = panel.querySelector("input");

  function addMessage(role, text, options) {
    var row = document.createElement("div");
    row.className = "cp-msg" + (role === "user" ? " user" : "");
    row.textContent = text || "";
    if (options && options.length) {
      var opts = document.createElement("div");
      opts.className = "cp-options";
      options.forEach(function (option) {
        var opt = document.createElement("button");
        opt.type = "button";
        opt.textContent = option;
        opt.onclick = function () { send(option); };
        opts.appendChild(opt);
      });
      row.appendChild(opts);
    }
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

  function send(text) {
    var value = (text || input.value || "").trim();
    if (!value) return;
    addMessage("user", value);
    input.value = "";

    var streamRow = null;
    var streamedText = "";

    fetch(apiBase + "/public/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chatbot_id: Number(chatbotId), message: value, session_id: sessionId })
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
            streamRow = addMessage("bot", streamedText);
          } else {
            streamRow.firstChild ? streamRow.firstChild.nodeValue = streamedText : streamRow.textContent = streamedText;
            messages.scrollTop = messages.scrollHeight;
          }
          return;
        }
        if (event.type === "final") {
          sessionId = event.session_id;
          var items = responseMessages(event);
          if (!streamRow) {
            items.forEach(function (item) { addMessage("bot", item.text, item.options || []); });
            return;
          }
          if (items[0]) {
            streamRow.textContent = streamedText || items[0].text || "";
            if (items[0].options && items[0].options.length) {
              var opts = document.createElement("div");
              opts.className = "cp-options";
              items[0].options.forEach(function (option) {
                var opt = document.createElement("button");
                opt.type = "button";
                opt.textContent = option;
                opt.onclick = function () { send(option); };
                opts.appendChild(opt);
              });
              streamRow.appendChild(opts);
            }
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
      showError(err.message || "Chat failed");
    });
  }

  button.onclick = function () { panel.classList.toggle("open"); };
  panel.querySelector("#cp-widget-close").onclick = function () { panel.classList.remove("open"); };
  form.onsubmit = function (event) {
    event.preventDefault();
    send();
  };
})();
"""
    script = script.replace("__DEFAULT_API_BASE__", default_api_base)
    return Response(content=script, media_type="application/javascript")
