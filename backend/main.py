import os

from fastapi import FastAPI
from routes.chatbot_routes import router as chatbot_router
from database.db import Base, engine
from models import chatbot, project
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
    {"name": "Admin Analytics", "description": "Admin analytics overview, sessions, and conversation details."},
]


def allowed_origins() -> list[str]:
    value = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL") or "http://localhost:4200"
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


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
app.include_router(admin_analytics_router, tags=["Admin Analytics"])

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
