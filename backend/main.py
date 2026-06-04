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


def allowed_origins() -> list[str]:
    value = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL") or "http://localhost:4200"
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


app = FastAPI()

app.include_router(auth_router)
app.include_router(version_router)
app.include_router(chatbot_router)
app.include_router(project_router)
app.include_router(llm_config_router)
app.include_router(knowledge_router)
app.include_router(flow_router)
app.include_router(chat_router)
app.include_router(public_router)
app.include_router(admin_analytics_router)

@app.get("/")
def home():
    return {"message": "Hello Balkis 🚀"}

@app.get("/health")
def health():
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
