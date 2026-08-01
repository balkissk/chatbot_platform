from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database.db import Base


class ProjectStatus(str, Enum):
    active = "active"
    draft = "draft"
    archived = "archived"
    disabled = "disabled"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    user_id = Column(Integer)
    status = Column(String, default=ProjectStatus.active.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
