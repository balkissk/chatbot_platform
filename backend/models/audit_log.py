from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String

from database.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_name = Column(String, nullable=True)
    actor_email = Column(String, nullable=True)
    actor_role = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)
    resource_id = Column(Integer, nullable=True, index=True)
    resource_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="success", index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
