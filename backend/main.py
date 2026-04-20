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


app = FastAPI()

app.include_router(version_router)
app.include_router(chatbot_router)
app.include_router(project_router)
app.include_router(llm_config_router)
app.include_router(chat_router)

@app.get("/")
def home():
    return {"message": "Hello Balkis 🚀"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)