from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.llm_config import LLMConfig
from models.llm_config_schema import LLMConfigCreate, LLMConfigResponse

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 🔥 CREATE or UPDATE
@router.post("/llm-config", response_model=LLMConfigResponse)
def create_or_update_config(data: LLMConfigCreate, db: Session = Depends(get_db)):

    config = db.query(LLMConfig).filter(
        LLMConfig.version_id == data.version_id
    ).first()

    if config:
        config.model = data.model
        config.temperature = data.temperature
        config.system_prompt = data.system_prompt
    else:
        config = LLMConfig(**data.dict())
        db.add(config)

    db.commit()
    db.refresh(config)

    return config


# 🔥 GET config
@router.get("/llm-config/{version_id}", response_model=LLMConfigResponse)
def get_config(version_id: int, db: Session = Depends(get_db)):

    config = db.query(LLMConfig).filter(
        LLMConfig.version_id == version_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=404,
            detail="LLM config not found"
        )

    return config