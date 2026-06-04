from sqlalchemy import Column, String, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship
from database.db import Base

class LLMConfig(Base):
    __tablename__ = "llm_configs"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id"), unique=True)

    model = Column(String, default="llama3")
    temperature = Column(Float, default=0.7)
    system_prompt = Column(String)

    version = relationship("VersionChatbot", back_populates="llm_config")