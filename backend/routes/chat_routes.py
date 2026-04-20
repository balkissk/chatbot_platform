from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db import SessionLocal
from models.version import VersionChatbot
from models.llm_config import LLMConfig
from models.chat_schema import ChatRequest

import requests
import os

router = APIRouter()

OPENROUTER_API_KEY = "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"  #

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/chat")
def chat(data: ChatRequest, db: Session = Depends(get_db)):

    # 1️⃣ نلقى version published
    version = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == data.chatbot_id,
        VersionChatbot.status == "published"
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="No published version")

    # 2️⃣ نلقى config
    config = db.query(LLMConfig).filter(
        LLMConfig.version_id == version.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="No config")

    # 3️⃣ call OpenRouter 🔥
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": config.system_prompt or "You are helpful"
                },
                {
                    "role": "user",
                    "content": data.message
                }
            ],
            "temperature": config.temperature
        }
    )

    result = response.json()
    print(response.status_code)
    print(response.text)




    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "response": result["choices"][0]["message"]["content"],
        "model_used": config.model,
        "version_used": version.id
    }