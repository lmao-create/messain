"""Configuration read from environment variables (optionally via a local .env file)."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv ships in requirements.txt
    pass

DEFAULT_DATABASE_PATH = "data/messenger.db"
DEFAULT_TOKEN_EXPIRE_DAYS = 30


def database_path() -> str:
    """Filesystem path of the SQLite database."""
    return os.environ.get("MESSAIN_DATABASE", DEFAULT_DATABASE_PATH)


def token_expire_days() -> int:
    """Number of days before an auth token expires."""
    raw = os.environ.get("MESSAIN_TOKEN_EXPIRE_DAYS", str(DEFAULT_TOKEN_EXPIRE_DAYS))
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_TOKEN_EXPIRE_DAYS
