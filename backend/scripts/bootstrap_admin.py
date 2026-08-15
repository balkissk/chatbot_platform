import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import load_environment
from database.db import SessionLocal
from models.user import User
from services.auth import hash_password


REQUIRED_ENV_VARS = (
    "BOOTSTRAP_ADMIN_NAME",
    "BOOTSTRAP_ADMIN_EMAIL",
    "BOOTSTRAP_ADMIN_PASSWORD",
)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> int:
    load_environment()

    name = required_env("BOOTSTRAP_ADMIN_NAME")
    email = required_env("BOOTSTRAP_ADMIN_EMAIL").lower()
    password = required_env("BOOTSTRAP_ADMIN_PASSWORD")

    db = SessionLocal()
    try:
        existing_admin = db.query(User.id).filter(User.role == "admin").first()
        if existing_admin:
            print("Admin already exists. No user created.")
            return 0

        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            status="active",
        )
        db.add(user)
        db.commit()
        print("Bootstrap admin created.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
