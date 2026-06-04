from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from database.db import Base


class Flow(Base):
    __tablename__ = "flows"

    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("versions.id"), unique=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    nodes = relationship("FlowNode", back_populates="flow")
    transitions = relationship("FlowTransition", back_populates="flow")


class FlowNode(Base):
    __tablename__ = "flow_nodes"

    id = Column(Integer, primary_key=True)
    flow_id = Column(Integer, ForeignKey("flows.id"))
    node_key = Column(String)
    type = Column(String)
    label = Column(String)
    config = Column(JSON)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)

    flow = relationship("Flow", back_populates="nodes")


class FlowTransition(Base):
    __tablename__ = "flow_transitions"

    id = Column(Integer, primary_key=True)
    flow_id = Column(Integer, ForeignKey("flows.id"))
    source_node_key = Column(String)
    target_node_key = Column(String)
    label = Column(String)
    condition = Column(String)

    flow = relationship("Flow", back_populates="transitions")
