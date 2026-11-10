"""SmartQueue API. Run: uvicorn app.main:app --reload   (docs at /docs)"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .api import router
from .config import ROOT
from .deps import service

@asynccontextmanager
async def lifespan(app: FastAPI):
    service.seed()
    yield

app = FastAPI(title="SmartQueue", version="2.0.0", description="AI-assisted support ticket triage", lifespan=lifespan)
app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")

@app.get("/", include_in_schema=False)
def index(): return FileResponse(ROOT / "app" / "static" / "index.html")

@app.get("/chat", include_in_schema=False)
def chat_page(): return FileResponse(ROOT / "app" / "static" / "chat.html")
