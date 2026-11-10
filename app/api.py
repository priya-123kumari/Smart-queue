from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from .deps import assistant, require_key, service
from .agent import is_high_risk
from .schemas import CategoryIn, ChatIn, DraftIn, FeedbackIn, TicketIn

router = APIRouter()
write = [Depends(require_key)]

def guard(fn, *a):
    try: return fn(*a)
    except LookupError as e: raise HTTPException(404, str(e))
    except ValueError as e: raise HTTPException(400, str(e))

async def aguard(coro):
    try: return await coro
    except LookupError as e: raise HTTPException(404, str(e))
    except ValueError as e: raise HTTPException(400, str(e))

@router.get("/health")
def health():
    return {"status": "ok", "llm": service.llm.enabled, "model": service.llm.model}

@router.get("/tickets")
def list_tickets(priority: str | None = None, category: str | None = None, team: str | None = None,
                 breached: bool | None = None, q: str | None = Query(None, max_length=100)):
    out = service.view(); stats = service.stats(out); cats = service.categories()
    f = [x for x in out if (not priority or x["priority"] == priority) and (not category or x["category"] == category) and (not team or x["team"] == team)
         and (breached is None or x["breached"] == breached) and (not q or q.lower() in (x["subject"] + x["body"] + x["customer"]).lower())]
    return {"tickets": f, "stats": stats, "categories": list(cats) + ["other"], "teams": sorted({v["team"] for v in cats.values()})}

@router.get("/tickets/{tid}")
def get_ticket(tid: str):
    t = next((x for x in service.view() if x["id"] == tid), None)
    if not t: raise HTTPException(404, f"ticket {tid} not found")
    return t

@router.post("/tickets", status_code=201, dependencies=write)
async def create_ticket(body: TicketIn, tasks: BackgroundTasks):
    tid = await service.ingest(body.model_dump())
    t = service.ticket_view(tid); risk = is_high_risk(t)
    if risk: tasks.add_task(service.escalate, tid)  # agentic flow runs after the response is sent
    return {"id": tid, "ticket": t, "high_risk": risk, "escalation": "queued" if risk else "not needed"}

@router.post("/tickets/{tid}/retriage", dependencies=write)
async def retriage(tid: str, tasks: BackgroundTasks):
    res = await aguard(service.retriage(tid))
    if res: tasks.add_task(service.escalate, tid)  # new AI urgency may make it high risk; already-alerted tickets are skipped
    return {"ok": bool(res), "llm": service.llm.enabled, "result": res}

@router.post("/tickets/{tid}/draft", dependencies=write)
async def draft(tid: str, body: DraftIn = DraftIn()):
    return await aguard(service.draft(tid, body.tone))

@router.post("/triage/backfill", status_code=202, dependencies=write)
async def backfill(tasks: BackgroundTasks):
    if not service.llm.enabled: raise HTTPException(409, "LLM triage is off (set ANTHROPIC_API_KEY). Rules are already applied.")
    tasks.add_task(service.backfill); return {"status": "started"}

@router.post("/tickets/{tid}/escalate", dependencies=write)
async def escalate(tid: str, force: bool = False):
    """Run the escalation agent now. force=true sends even if the ticket is not high risk or was already alerted."""
    return await aguard(service.escalate(tid, force))

@router.get("/alerts")
def alerts(limit: int = Query(50, ge=1, le=500)):
    return {"email_configured": service.mailer.configured, "alerts": service.alerts(limit)}

@router.post("/feedback", dependencies=write)
def feedback(body: FeedbackIn):
    guard(service.feedback, body.ticket_id, body.category); return {"ok": True}

@router.get("/categories")
def categories(): return service.categories()

@router.post("/categories", status_code=201, dependencies=write)
def add_category(body: CategoryIn):
    return {"name": guard(service.add_category, body.name, body.keywords, body.team, body.base)}

@router.post("/reset", dependencies=write)
def reset(): service.reset(); return {"ok": True}

@router.post("/chat")
async def chat(body: ChatIn):
    """Chat with the AI assistant about tickets, customers and the knowledge base. Read-only: it never sends email or changes data."""
    return await aguard(assistant.reply([m.model_dump() for m in body.messages]))
