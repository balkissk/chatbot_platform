import os
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config.settings import get_settings

settings = get_settings()
DATABASE_URL = settings.database_url


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 5, 1)
DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 10, 0)
DB_POOL_TIMEOUT = _int_env("DB_POOL_TIMEOUT", 30, 1)
DB_POOL_RECYCLE = _int_env("DB_POOL_RECYCLE", 1800, 1)


def _engine_kwargs(database_url: str) -> dict:
    kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": DB_POOL_RECYCLE,
    }
    if not urlparse(database_url).scheme.startswith("sqlite"):
        kwargs.update({
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_MAX_OVERFLOW,
            "pool_timeout": DB_POOL_TIMEOUT,
        })
    return kwargs


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

Base = declarative_base() 
