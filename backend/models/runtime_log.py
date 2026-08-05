from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from database.db import Base


class RuntimeLog(Base):
    __tablename__ = "runtime_logs"

    id = Column(Integer, primary_key=True)
    chatbot_id = Column(Integer, ForeignKey("chatbots.id", ondelete="SET NULL"), nullable=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id", ondelete="SET NULL"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversation_sessions.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    channel = Column(String, nullable=False, default="unknown", index=True)
    execution_id = Column(String, nullable=True, index=True)
    execution_mode = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, index=True)
    rag_used = Column(Boolean, nullable=False, default=False)
    response_time_ms = Column(Integer, nullable=True)
    failure_category = Column(String, nullable=True, index=True)
    current_block = Column(String, nullable=True)
    retrieval_count = Column(Integer, nullable=True)
    provider = Column(String, nullable=True)
    error_type = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
