import hmac
from fastapi import Header, HTTPException
from . import config
from .config import ROOT
from .db import DB
from .llm import LLMTriager
from .services import TriageService
from .chat import ChatAssistant

service = TriageService(DB(config.DB_PATH), LLMTriager(), ROOT / "data")
assistant = ChatAssistant(service.llm, service)

def require_key(x_api_key: str | None = Header(default=None)):
    """Optional auth: only enforced when SMARTQUEUE_API_KEY is set."""
    if config.API_KEY and not hmac.compare_digest(x_api_key or "", config.API_KEY):
        raise HTTPException(401, "Missing or invalid X-API-Key header")
