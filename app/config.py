import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

# Load settings from .env automatically (skipped under pytest so tests never hit the real API).
if "pytest" not in sys.modules:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

DB_PATH = os.getenv("SMARTQUEUE_DB", str(ROOT / "data" / "smartqueue.db"))
MODEL = os.getenv("SMARTQUEUE_MODEL", "claude-sonnet-5-5")
# Optional: point the LLM client at an Anthropic-compatible server instead of api.anthropic.com,
# e.g. a free local Ollama (LLM_BASE_URL=http://localhost:11434, SMARTQUEUE_MODEL=qwen2.5:3b). No API key needed then.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip() or None
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "") or (180 if LLM_BASE_URL else 15))  # local CPU models are slow
API_KEY = os.getenv("SMARTQUEUE_API_KEY") or None  # optional: protects mutating routes via X-API-Key

# High-risk ticket alerts (see app/agent.py). Without SMTP_HOST, emails are stored in the outbox only (dry run).
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")          # comma-separated on-call addresses
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = os.getenv("SMTP_PORT", "587") or "587"
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
