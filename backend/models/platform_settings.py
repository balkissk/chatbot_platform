from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from database.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id = Column(Integer, primary_key=True)
    platform_name = Column(String(80), nullable=False)
    support_email = Column(String(255), nullable=False)
    default_page_size = Column(Integer, nullable=False, default=10)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
