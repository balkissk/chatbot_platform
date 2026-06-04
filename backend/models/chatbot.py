from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from datetime import datetime
from database.db import Base

class Chatbot(Base):
    __tablename__ = "chatbots"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    language = Column(String)
    type = Column(String, default="builder")
    purpose = Column(String, default="custom")
    mode = Column(String, default="builder")
    channel = Column(String, default="web_widget")
    build_method = Column(String, default="blank")
    template_key = Column(String)
    is_active = Column(Boolean, default=True)
    active_version_id = Column(Integer, ForeignKey("versions.id"), nullable=True)
    public_api_key = Column(String, nullable=True, index=True)
    public_api_enabled = Column(Boolean, default=True)
    rag_settings = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    project_id = Column(Integer, ForeignKey("projects.id"))
