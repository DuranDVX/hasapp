"""Settings. Every value can be overridden with an environment variable or .env."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

APP_NAME = os.getenv("HAS_APP_NAME", "SiteSafe")   # working name, change in one place
WEB = ROOT / "web"
DATA = Path(os.getenv("HAS_DATA", ROOT / "data"))
FILES = DATA / "files"
FILES.mkdir(parents=True, exist_ok=True)

# SQLite for development; Postgres in production (Railway sets DATABASE_URL).
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA / 'hasapp.db'}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

MODEL = os.getenv("HAS_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("HAS_EFFORT", "low")
AI_PER_HOUR = int(os.getenv("HAS_AI_PER_HOUR", "60"))   # spend guard per company
WHISPER_MODEL = os.getenv("HAS_WHISPER", "small")

# Optional text-to-speech for toolbox talks (Azure Speech). Without a key the
# app shows the text and the foreman reads it aloud or records it.
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "southafricanorth")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8500").rstrip("/")
CRON_TOKEN = os.getenv("CRON_TOKEN", "")          # protects /api/cron/*
SECRET_KEY = os.getenv("HAS_SECRET_KEY", "")      # signs file links; else data/secret.key
SESSION_DAYS = 90                                   # site tablets stay logged in
EXPIRY_WARN_DAYS = 30
