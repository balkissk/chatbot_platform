from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.db import SessionLocal
from models.version import VersionChatbot
from models.version_schema import VersionCreate
from models.llm_config import LLMConfig

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# CREATE VERSION
@router.post("/versions")
def create_version(version: VersionCreate, db: Session = Depends(get_db)):

    # نجيب آخر version number
    last_version = db.query(VersionChatbot) \
        .filter(VersionChatbot.chatbot_id == version.chatbot_id) \
        .order_by(VersionChatbot.version_number.desc()) \
        .first()

    new_number = 1 if not last_version else last_version.version_number + 1

    new_version = VersionChatbot(
        chatbot_id=version.chatbot_id,
        version_number=new_number,
        status="draft"
    )

    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    return new_version
    default_config = LLMConfig(
    version_id=new_version.id,
    model="gpt-4o-mini",
    temperature=0.7,
    system_prompt="You are a helpful assistant"
)

    db.add(default_config)
    db.commit()

    return new_version


# GET versions by chatbot
@router.get("/chatbots/{chatbot_id}/versions")
def get_versions(chatbot_id: int, db: Session = Depends(get_db)):
    return db.query(VersionChatbot) \
        .filter(VersionChatbot.chatbot_id == chatbot_id) \
        .all()

# PUBLISH VERSION
@router.put("/versions/{version_id}/publish")
def publish_version(version_id: int, db: Session = Depends(get_db)):

    version = db.query(VersionChatbot).filter(
        VersionChatbot.id == version_id
    ).first()

    if not version:
        return {"error": "Version not found"}

    # 🔥 نلقاو كل versions لنفس chatbot
    all_versions = db.query(VersionChatbot).filter(
        VersionChatbot.chatbot_id == version.chatbot_id
    ).all()

    # 🔥 نعمل archive للكل
    for v in all_versions:
        v.status = "archived"

    # 🔥 نخلي الحالية published
    version.status = "published"

    db.commit()

    return {"message": "Version published"}

# ARCHIVE VERSION
@router.put("/versions/{version_id}/archive")
def archive_version(version_id: int, db: Session = Depends(get_db)):

    version = db.query(VersionChatbot).filter(
        VersionChatbot.id == version_id
    ).first()

    if not version:
        return {"error": "Version not found"}

    version.status = "archived"
    db.commit()

    return {"message": "Version archived"}