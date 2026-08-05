from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from database.db import Base


class VersionSmokeTest(Base):
    __tablename__ = "version_smoke_tests"

    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False, index=True)
    chatbot_id = Column(Integer, ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False, index=True)
    tested_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    test_mode = Column(String, nullable=False, default="auto")
    status = Column(String, nullable=False, index=True)
    failure_category = Column(String, nullable=True, index=True)
    latency_ms = Column(Integer, nullable=True)
    trace = Column(JSON, default=dict)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
