import json
import os

from fastapi import FastAPI
from routes.chatbot_routes import router as chatbot_router
from database.db import Base, engine
from models import chatbot, project, flow_template
from routes.project_routes import router as project_router
from routes.version_routes import router as version_router
from routes.llm_config_routes import router as llm_config_router
from fastapi.middleware.cors import CORSMiddleware
from models import llm_config
from routes.chat_routes import router as chat_router
from routes.knowledge_routes import router as knowledge_router
from routes.auth_routes import router as auth_router
from routes.flow_routes import router as flow_router
from routes.public_routes import router as public_router
from routes.admin_analytics_routes import router as admin_analytics_router
from routes.health_routes import router as health_router
from routes.channel_routes import router as channel_router
from routes.evaluation_routes import router as evaluation_router
from routes.legal_routes import router as legal_router
from routes.platform_settings_routes import router as platform_settings_router
from services.ai_provider import AIProviderError, azure_openai_configuration_warnings, validate_ai_configuration, warm_ai_client
from services.embeddings import EmbeddingError, validate_embedding_configuration
from config.settings import load_environment

load_environment()

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]


openapi_tags = [
    {"name": "System", "description": "Health checks and API status."},
    {"name": "Auth", "description": "Authentication, profile, password management, and user administration."},
    {"name": "Projects", "description": "Project creation, listing, update, and deletion."},
    {"name": "Chatbots", "description": "Chatbot configuration, public API keys, status, and project chatbot lists."},
    {"name": "Versions", "description": "Chatbot version lifecycle: create, duplicate, publish, archive, and delete."},
    {"name": "LLM Config", "description": "Model, temperature, and system prompt configuration."},
    {"name": "Knowledge Base", "description": "Documents, chunks, embeddings, and RAG testing."},
    {"name": "Flow Builder", "description": "Builder flows, nodes, transitions, and visual chatbot logic."},
    {"name": "Chat", "description": "Authenticated chat sessions and streaming chat endpoints."},
    {"name": "Public API", "description": "Public chatbot pages, widget script, and external API chat endpoints."},
    {"name": "Channels", "description": "Channel deployment settings for public chat, widget, and REST API."},
    {"name": "Evaluations", "description": "Assistant quality datasets, evaluation runs, regression comparison, and publish gates."},
    {"name": "Admin Analytics", "description": "Admin analytics overview, sessions, and conversation details."},
]


def parse_allowed_origins(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []

    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("ALLOWED_ORIGINS must be a JSON array or comma-separated list.") from exc

        if not isinstance(parsed, list) or not all(isinstance(origin, str) for origin in parsed):
            raise ValueError("ALLOWED_ORIGINS JSON value must be a list of strings.")
        raw_origins = parsed
    else:
        raw_origins = value.split(",")

    origins = [origin.strip().rstrip("/") for origin in raw_origins if origin.strip()]
    if "*" in origins:
        raise ValueError("Wildcard CORS origins are not allowed when credentials are enabled.")
    return origins


def allowed_origins() -> list[str]:
    configured_origins = []

    for env_name in ("ALLOWED_ORIGINS", "FRONTEND_URL", "FRONTEND_BASE_URL"):
        configured_origins.extend(parse_allowed_origins(os.getenv(env_name, "")))

    origins = configured_origins or DEFAULT_ALLOWED_ORIGINS
    return list(dict.fromkeys(origins))


app = FastAPI(
    title="ChatBot Factory API",
    description="Backend API for chatbot project management, flow building, knowledge bases, and public chat.",
    version="1.0.0",
    openapi_tags=openapi_tags,
)

app.include_router(auth_router)
app.include_router(project_router, tags=["Projects"])
app.include_router(chatbot_router, tags=["Chatbots"])
app.include_router(version_router, tags=["Versions"])
app.include_router(llm_config_router, tags=["LLM Config"])
app.include_router(knowledge_router, tags=["Knowledge Base"])
app.include_router(flow_router, tags=["Flow Builder"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(public_router, tags=["Public API"])
app.include_router(channel_router, tags=["Channels"])
app.include_router(evaluation_router)
app.include_router(admin_analytics_router, tags=["Admin Analytics"])
app.include_router(health_router)
app.include_router(legal_router)
app.include_router(platform_settings_router)

@app.get("/", tags=["System"])
def home():
    return {"message": "Hello Balkis 🚀"}

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def validate_external_ai_configuration() -> None:
    try:
        validate_ai_configuration()
        validate_embedding_configuration()
        warm_ai_client()
    except (AIProviderError, EmbeddingError) as exc:
        raise RuntimeError(f"External AI configuration error: {exc}") from exc

    for warning in azure_openai_configuration_warnings():
        print(f"External AI configuration warning: {warning}")
