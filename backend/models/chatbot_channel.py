from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from database.db import Base


class ChatbotChannel(Base):
    __tablename__ = "chatbot_channels"

    id = Column(Integer, primary_key=True)
    chatbot_id = Column(Integer, ForeignKey("chatbots.id"), nullable=False, index=True)
    channel_type = Column(String, nullable=False, index=True)
    status = Column(String, default="not_configured", nullable=False)
    config_json = Column(JSON, default=dict)
    deployed_version_id = Column(Integer, ForeignKey("versions.id"), nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_verification_at = Column(DateTime, nullable=True)
    last_incoming_message_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChannelLog(Base):
    __tablename__ = "channel_logs"

    id = Column(Integer, primary_key=True)
    chatbot_id = Column(Integer, ForeignKey("chatbots.id"), nullable=False, index=True)
    channel_type = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    message = Column(String, nullable=True)
    status = Column(String, nullable=False, default="info")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
