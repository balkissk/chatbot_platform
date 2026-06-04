from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="end_user")
    status = Column(String, default="active")
    email_verified_at = Column(DateTime, nullable=True)
    email_verification_token = Column(String, nullable=True, index=True)
    email_verification_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
