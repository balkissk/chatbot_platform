from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from database.db import Base


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(Integer, primary_key=True)
    chatbot_id = Column(Integer, ForeignKey("chatbots.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("versions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    current_node_key = Column(String, nullable=True)
    variables = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ConversationMessage", back_populates="session")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("conversation_sessions.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ConversationSession", back_populates="messages")
