from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config.settings import get_settings

settings = get_settings()
DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base() 
