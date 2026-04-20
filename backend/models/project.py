from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database.db import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)