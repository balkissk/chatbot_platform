from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from database.db import Base


class FlowTemplate(Base):
    __tablename__ = "flow_templates"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    purpose = Column(String, default="custom", index=True)
    is_exposed = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source_flow_id = Column(Integer, ForeignKey("flows.id"), nullable=True)
    nodes = Column(JSON, default=list)
    transitions = Column(JSON, default=list)
    test_scenarios = Column(JSON, default=list)
    current_revision_number = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User")


class FlowTemplateRevision(Base):
    __tablename__ = "flow_template_revisions"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("flow_templates.id"), nullable=False, index=True)
    revision_number = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    purpose = Column(String, default="custom")
    nodes = Column(JSON, default=list)
    transitions = Column(JSON, default=list)
    test_scenarios = Column(JSON, default=list)
    change_note = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    template = relationship("FlowTemplate")
    creator = relationship("User")
