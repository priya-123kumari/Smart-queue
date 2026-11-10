"""HTTP tests. Need: pip install -r requirements.txt, then pytest."""
import os, tempfile
os.environ["SMARTQUEUE_DB"] = os.path.join(tempfile.mkdtemp(), "api.db")
os.environ.pop("ANTHROPIC_API_KEY", None)
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client: yield client

def test_health_and_queue(c):
    assert c.get("/api/health").json()["status"] == "ok"
    d = c.get("/api/tickets").json(); assert len(d["tickets"]) >= 80 and d["stats"]["incidents"]

def test_filters(c):
    p1 = c.get("/api/tickets", params={"priority": "P1"}).json()["tickets"]
    assert p1 and all(t["priority"] == "P1" for t in p1)

def test_create_validate_and_missing(c):
    r = c.post("/api/tickets", json={"subject": "How do I invite teammates?", "body": "need steps"}); assert r.status_code == 201
    assert r.json()["ticket"]["category"] == "how_to"
    assert c.post("/api/tickets", json={"subject": "", "body": "x"}).status_code == 422
    assert c.get("/api/tickets/T-nope").status_code == 404

def test_category_feedback_and_ai_off(c):
    assert c.post("/api/categories", json={"name": "Legal", "keywords": "gdpr, subpoena", "team": "Legal", "base": 3}).status_code == 201
    tid = c.get("/api/tickets").json()["tickets"][0]["id"]
    assert c.post("/api/feedback", json={"ticket_id": tid, "category": "legal"}).status_code == 200
    assert c.post("/api/feedback", json={"ticket_id": tid, "category": "zzz"}).status_code == 400
    assert c.post("/api/triage/backfill").status_code == 409  # no API key in tests

def test_high_risk_ticket_triggers_escalation(c):
    r = c.post("/api/tickets", json={"customer_name": "Ops", "plan_tier": "enterprise", "channel": "twitter",
                                     "subject": "Production down for all users!!!", "body": "outage, data loss, urgent, unacceptable"}).json()
    assert r["high_risk"] and r["escalation"] == "queued"
    a = c.get("/api/alerts").json()
    assert a["email_configured"] is False and a["alerts"][0]["ticket_id"] == r["id"] and a["alerts"][0]["status"] == "dry_run"
    assert c.post(f"/api/tickets/{r['id']}/escalate").json()["status"] == "skipped"
    assert c.post("/api/tickets/T-nope/escalate").status_code == 404

def test_chat_rules_fallback_and_validation(c):
    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": "show P1 tickets"}]}).json()
    assert r["mode"] == "rules" and "P1" in r["reply"]
    tid = c.get("/api/tickets").json()["tickets"][0]["id"]
    assert tid in c.post("/api/chat", json={"messages": [{"role": "user", "content": f"what about {tid}?"}]}).json()["reply"]
    assert c.post("/api/chat", json={"messages": []}).status_code == 422
    assert c.post("/api/chat", json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code == 400
