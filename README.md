# SmartQueue v2: FastAPI + LLM support-ticket triage

Full-stack Python app. FastAPI backend, SQLite storage, a dashboard served from the same process, and an Anthropic LLM layer that falls back to deterministic rules.

## Run (Python 3.10+)
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...      # optional; without it the app runs on rules
    uvicorn app.main:app --reload            # UI: http://localhost:8000   API docs: http://localhost:8000/docs
    docker build -t smartqueue . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY smartqueue

Tests: `python -m unittest tests.test_service` (no extra deps) and `pytest` (HTTP tests, needs requirements).
Regenerate sample data: `python data/gen.py`, delete `data/smartqueue.db`.

## Layout
    app/main.py       FastAPI app, lifespan seeding, static UI
    app/api.py        routes (/api/*)           app/schemas.py  pydantic request models
    app/services.py   pipeline + persistence    app/llm.py      Anthropic client, validation, circuit breaker
    app/rules.py      pure rule engine          app/db.py       SQLite wrapper
    app/deps.py       singletons + optional X-API-Key auth      app/static/index.html  dashboard
    data/             categories, knowledge base, 80 sample tickets, held-out test set

## How the LLM is used
1. **Triage on ingest**: `POST /api/tickets` stores the ticket, then asks the model for category, sentiment (-2..2), urgency (1..5), language, a 20-word summary and a draft reply grounded in the knowledge base. Output is requested as JSON, parsed defensively and validated (`llm.clean`): unknown labels are rejected and numbers clamped.
2. **Hybrid decision**: category = agent correction > valid LLM label > rules. The LLM's urgency and sentiment feed the explainable priority score as extra points ("AI urgency 5/5", "Negative tone (AI)"), so you can still see why a ticket ranked where it did.
3. **Failure handling**: timeout 15s, one retry, then rules. After 3 consecutive failures a circuit breaker disables the LLM for 60s so the queue stays fast.
4. **Prompt-injection hygiene**: ticket text is wrapped in `<ticket>` tags and the system prompt says to treat it as data. The model cannot trigger actions; its output is only classification text, validated before use.
5. **On-demand**: `POST /api/tickets/{id}/draft` (tone), `/retriage`, and `POST /api/triage/backfill` (background, 5 concurrent calls) for the seeded tickets.

## Agentic escalation (high-risk email alerts)
A new ticket is **high risk** when it scores P1 or the AI rates urgency 5/5. `POST /api/tickets` then queues the escalation agent (`app/agent.py`) in the background:
1. Claude gets read-only tools (`get_ticket`, `get_customer_history`, `search_kb`) and investigates in a short loop (max 6 steps).
2. It calls `send_escalation_email` once with severity, subject and body. The recipient is fixed by `ALERT_EMAIL_TO`; the model cannot change it.
3. If the LLM is off or fails, a rules-based alert email is sent instead, so a high-risk ticket is never silent.
4. Every alert is stored (`GET /api/alerts`) with its tool steps; a ticket is alerted once (`escalated: true`). `POST /api/tickets/{id}/escalate?force=true` re-sends by hand.

Email uses SMTP settings from `.env` (see `.env.example`). Without `SMTP_HOST` it is a dry run: alerts are saved but not sent. Seeded sample tickets are not auto-escalated.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | status, LLM on/off |
| GET | /api/tickets | ranked queue; filters `priority, category, team, breached, q` |
| GET | /api/tickets/{id} | one ticket with reasons and reply |
| POST | /api/tickets | create and triage |
| POST | /api/tickets/{id}/retriage, /draft | LLM re-run, tone-controlled reply |
| POST | /api/triage/backfill | LLM-triage tickets that have no AI result |
| POST | /api/feedback | agent label correction (teaches the rules) |
| GET/POST | /api/categories | list / add a category live |
| POST | /api/reset | wipe and reseed |

Set `SMARTQUEUE_API_KEY` to require an `X-API-Key` header on write routes (the bundled UI does not send one, so use it for API-only deployments).

## Tradeoffs to explain in the pitch
- LLM first gives better handling of Hinglish and nuance; rules give speed, zero cost and explainability. Hybrid keeps both, and the app never depends on the API being up.
- SQLite is fine for a demo and a few thousand tickets a day; move to Postgres and a task queue (Celery/Arq) for scale, and replace pairwise clustering with embeddings or MinHash.
- Incident detection is rule-based on purpose (cheap, deterministic); the LLM could name and summarise the incident as a next step.
- Cost control: one short call per ticket, 500 max tokens; cache by text hash if you expect repeats.
- Priority weights and thresholds are hand-set. Measure P1 recall on labelled data before trusting them.

## Known limits
- The HTTP layer (`app/api.py`, `main.py`) was written without being run in the build sandbox (FastAPI could not be installed there). The service, rules and LLM layers are tested; run `pytest` after installing to verify the routes.
- The LLM path is tested with a fake client, not the live API.
