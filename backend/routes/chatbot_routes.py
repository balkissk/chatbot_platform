from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.db import SessionLocal
from models.chatbot import Chatbot
from models.chatbot_schema import ChatbotCreate

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/chatbots")
def create_chatbot(chatbot: ChatbotCreate, db: Session = Depends(get_db)):
    new_chatbot = Chatbot(
        name=chatbot.name,
        language=chatbot.language,
        type=chatbot.type,
        project_id=chatbot.project_id
    )

    db.add(new_chatbot)
    db.commit()
    db.refresh(new_chatbot)

    return new_chatbot

@router.get("/chatbots")
def get_chatbots(db: Session = Depends(get_db)):
    return db.query(Chatbot).all()

@router.delete("/chatbots/{id}")
def delete_chatbot(id: int, db: Session = Depends(get_db)):
    chatbot = db.query(Chatbot).filter(Chatbot.id == id).first()
    db.delete(chatbot)
    db.commit()

    return {"message": "deleted"}
@router.get("/projects/{project_id}/chatbots")
def get_chatbots_by_project(project_id: int, db: Session = Depends(get_db)):
    return db.query(Chatbot).filter(Chatbot.project_id == project_id).all()