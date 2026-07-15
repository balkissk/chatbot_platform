import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import dotenv_values, load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
VALID_ENVIRONMENTS = {"development", "production"}
_LOADED = False


def _load_profile_file(path: Path, protected_keys: set[str]) -> None:
    if not path.exists():
        return

    values = dotenv_values(path)
    if "DATABASE_URL" not in values and "DATABASE_URL" not in protected_keys:
        os.environ.pop("DATABASE_URL", None)

    for key, value in values.items():
        if key not in protected_keys and value is not None:
            os.environ[key] = value


def load_environment() -> str:
    global _LOADED
    if _LOADED:
        return os.getenv("ENVIRONMENT", "development").strip().lower()

    protected_keys = set(os.environ.keys())
    load_dotenv(BACKEND_DIR / ".env", override=False)

    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError(
            f"Invalid ENVIRONMENT '{environment}'. Use one of: {', '.join(sorted(VALID_ENVIRONMENTS))}."
        )

    _load_profile_file(BACKEND_DIR / f".env.{environment}", protected_keys)
    os.environ["ENVIRONMENT"] = environment
    _LOADED = True
    return environment


def _database_url_from_parts(environment: str) -> str:
    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER") or "postgres"
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or "1234"
    host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST") or "localhost"
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"
    database = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME") or "chatbot_db"
    sslmode = os.getenv("POSTGRES_SSLMODE") or os.getenv("DB_SSLMODE")

    auth = f"{quote_plus(user)}:{quote_plus(password)}"
    url = f"postgresql://{auth}@{host}:{port}/{database}"
    if sslmode or environment == "production":
        url += f"?sslmode={sslmode or 'require'}"
    return url


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    frontend_base_url: str
    backend_base_url: str


def get_settings() -> Settings:
    environment = load_environment()
    database_url = os.getenv("DATABASE_URL") or _database_url_from_parts(environment)
    frontend_base_url = (os.getenv("FRONTEND_BASE_URL") or "http://localhost:4200").rstrip("/")
    backend_base_url = (os.getenv("BACKEND_BASE_URL") or os.getenv("API_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
    return Settings(
        environment=environment,
        database_url=database_url,
        frontend_base_url=frontend_base_url,
        backend_base_url=backend_base_url,
    )
