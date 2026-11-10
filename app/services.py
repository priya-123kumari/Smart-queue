"""Business logic: persistence + hybrid (LLM first, rules fallback) triage pipeline."""
import asyncio, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from . import rules
from .agent import EscalationAgent, is_high_risk
from .notify import Mailer
from .rules import SLA, STOP, TIER, toks

def utcnow(): return datetime.now(timezone.utc)

class TriageService:
    def __init__(self, db, llm, data_dir, mailer=None):
        self.db, self.llm, self.data = db, llm, Path(data_dir)
        self.mailer = mailer or Mailer()
        self.agent = EscalationAgent(llm, self.mailer)
        self.kb = json.loads((self.data / "kb.json").read_text(encoding="utf-8"))

    # ---------- setup ----------
    def seed(self):
        if not self.db.q("SELECT 1 FROM categories LIMIT 1"):
            for n, v in json.loads((self.data / "categories.json").read_text(encoding="utf-8")).items():
                self.db.x("INSERT INTO categories VALUES(?,?,?,?)", (n, v["team"], v["base"], json.dumps(v["keywords"])))
        if not self.db.q("SELECT 1 FROM tickets LIMIT 1"):
            raw = json.loads((self.data / "tickets.json").read_text(encoding="utf-8"))
            off = utcnow().replace(tzinfo=None) - timedelta(minutes=10) - max(datetime.fromisoformat(t["created_at"]) for t in raw)
            for t in raw:  # shift sample times so the newest ticket is 10 minutes old and SLAs look live
                ts = (datetime.fromisoformat(t["created_at"]) + off).replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
                self.db.x("INSERT INTO tickets(id,customer_name,plan_tier,subject,body,channel,created_at) VALUES(?,?,?,?,?,?,?)",
                          (t["ticket_id"], t["customer_name"], t["plan_tier"], t["subject"], t["body"], t["channel"], ts))

    def reset(self):
        for tbl in ("tickets", "categories", "learned", "alerts"): self.db.x(f"DELETE FROM {tbl}")
        self.seed()

    def categories(self):
        return {r["name"]: {"team": r["team"], "base": r["base"], "keywords": json.loads(r["keywords"])} for r in self.db.q("SELECT * FROM categories")}

    def learned(self):
        out = {}
        for r in self.db.q("SELECT * FROM learned"): out.setdefault(r["category"], {})[r["word"]] = r["n"]
        return out

    def _ticket(self, tid):
        r = self.db.q("SELECT * FROM tickets WHERE id=?", (tid,))
        if not r: raise LookupError(f"ticket {tid} not found")
        return r[0]

    # ---------- commands ----------
    async def ingest(self, d):
        tid = f"T-{1001 + self.db.q('SELECT COUNT(*) c FROM tickets')[0]['c']}"
        while self.db.q("SELECT 1 FROM tickets WHERE id=?", (tid,)): tid += "x"
        self.db.x("INSERT INTO tickets(id,customer_name,plan_tier,subject,body,channel,created_at) VALUES(?,?,?,?,?,?,?)",
                  (tid, d["customer_name"].strip() or "Anonymous", d["plan_tier"], d["subject"].strip(), d["body"].strip(), d["channel"], utcnow().isoformat(timespec="seconds")))
        await self.retriage(tid)
        return tid

    async def retriage(self, tid):
        """Ask the LLM to triage one ticket. Returns the stored result, or None (rules will be used)."""
        t = self._ticket(tid)
        res = await self.llm.triage(t, self.categories(), self.kb)
        if res: self.db.x("UPDATE tickets SET triage=? WHERE id=?", (json.dumps(res), tid))
        return res

    async def backfill(self, limit=100, concurrency=5):
        ids = [r["id"] for r in self.db.q("SELECT id FROM tickets WHERE triage IS NULL ORDER BY created_at DESC LIMIT ?", (limit,))]
        sem = asyncio.Semaphore(1 if getattr(self.llm, "local", False) else concurrency)  # parallel calls just queue (and time out) on a local CPU model
        async def one(i):
            async with sem: return await self.retriage(i)
        res = await asyncio.gather(*(one(i) for i in ids))
        return {"attempted": len(ids), "succeeded": sum(1 for r in res if r)}

    async def draft(self, tid, tone):
        t = self._ticket(tid)
        text = await self.llm.draft(t, tone, self.kb)
        return {"reply": text or rules.draft(t, self.kb, None), "source": "llm" if text else "kb"}

    def add_category(self, name, keywords, team, base):
        name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        kws = [k.strip().lower() for k in (keywords.split(",") if isinstance(keywords, str) else keywords) if k.strip()]
        if not name or not kws: raise ValueError("name and keywords are required")
        self.db.x("INSERT OR REPLACE INTO categories VALUES(?,?,?,?)", (name, team or "Support L1", base, json.dumps(kws)))
        return name

    def feedback(self, tid, cat):
        t = self._ticket(tid)
        if cat not in self.categories() and cat != "other": raise ValueError(f"unknown category {cat}")
        self.db.x("UPDATE tickets SET override=? WHERE id=?", (cat, tid))
        for w in set(toks(t["subject"])):
            if w not in STOP and len(w) > 3:
                self.db.x("INSERT INTO learned VALUES(?,?,1) ON CONFLICT(category,word) DO UPDATE SET n=n+1", (cat, w))

    # ---------- escalation (agentic flow) ----------
    async def escalate(self, tid, force=False):
        """Run the escalation agent for a high-risk ticket. Skips low-risk or already-alerted tickets unless force=True."""
        t = self.ticket_view(tid)
        reasons = is_high_risk(t)
        if not reasons and not force: return {"ticket_id": tid, "status": "skipped", "reason": "not high risk"}
        if not force and self.db.q("SELECT 1 FROM alerts WHERE ticket_id=? AND status IN ('sent','dry_run')", (tid,)):
            return {"ticket_id": tid, "status": "skipped", "reason": "already escalated"}
        reasons = reasons or ["manual escalation"]
        a = await self.agent.run(t, reasons, self)
        self.db.x("INSERT INTO alerts(ticket_id,created_at,reasons,mode,severity,status,error,to_addr,subject,body,steps) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (tid, utcnow().isoformat(timespec="seconds"), json.dumps(reasons), a["mode"], a["severity"], a["status"], a["error"], a["to"],
                   a["subject"], a["body"], json.dumps(a["steps"])))
        return {"ticket_id": tid, "reasons": reasons, **a}

    def alerts(self, limit=50):
        rows = self.db.q("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows: r["reasons"], r["steps"] = json.loads(r["reasons"] or "[]"), json.loads(r["steps"] or "[]")
        return rows

    # agent tools (read-only)
    def ticket_view(self, tid):
        t = next((x for x in self.view() if x["id"] == tid), None)
        if not t: raise LookupError(f"ticket {tid} not found")
        return t

    def customer_history(self, name, exclude=None):
        rows = [x for x in self.view() if x["customer"].lower() == name.strip().lower() and x["id"] != exclude]
        rows.sort(key=lambda x: x["created_at"], reverse=True)
        return [{k: x[k] for k in ("id", "created_at", "subject", "category", "priority")} for x in rows[:10]]

    def search_kb(self, query):
        q = set(toks(query))
        scored = sorted(((len(q & set(toks(k["title"] + " " + " ".join(k["keywords"])))), k) for k in self.kb), key=lambda p: -p[0])
        return [{"title": k["title"], "answer": k["answer"]} for s, k in scored[:3] if s]

    # ---------- queries ----------
    def view(self):
        cats, learned, ref = self.categories(), self.learned(), utcnow()
        alerted = {r["ticket_id"] for r in self.db.q("SELECT ticket_id FROM alerts WHERE status IN ('sent','dry_run')")}
        ts = self.db.q("SELECT * FROM tickets ORDER BY created_at")
        valid = set(cats) | {"other"}
        for t in ts:
            t["_dt"] = datetime.fromisoformat(t["created_at"])
            t["ai"] = json.loads(t["triage"]) if t["triage"] else None
            if t["override"] in valid: t["_c"] = (t["override"], 1.0, ["agent correction"], "agent")
            elif t["ai"] and t["ai"]["category"] in valid: t["_c"] = (t["ai"]["category"], 0.9, [], "llm")
            else:
                c, conf, why = rules.classify(t, cats, learned); t["_c"] = (c, conf, why, "rules")
        inc, n, bycat = {}, 0, {}
        for t in ts: bycat.setdefault(t["_c"][0], []).append(t)
        for c, g in bycat.items():
            if c == "other" or cats.get(c, {}).get("base", 0) < 2: continue  # only service-impacting categories form incidents
            for grp in rules.clusters(g):
                if len(grp) >= 4:
                    n += 1
                    for i in grp: inc[g[i]["id"]] = (f"INC-{n}", len(grp))
        out = []
        for t in ts:
            c, conf, why, src = t["_c"]; i = inc.get(t["id"], (None, 0)); ai = t["ai"]
            rep = sum(1 for o in ts if o["customer_name"] == t["customer_name"] and o["_dt"] < t["_dt"] and (t["_dt"] - o["_dt"]).total_seconds() <= 172800)
            p, s, reasons = rules.priority(t, c, cats, i[1], rep, ai); team, rr = rules.route(c, p, t, cats)
            rem = (t["_dt"] + timedelta(minutes=SLA[p]) - ref).total_seconds() / 60
            if not i[0] and ai and ai.get("reply"): reply, rsrc = ai["reply"], "llm"
            else: reply, rsrc = rules.draft(t, self.kb, i[0]), "kb"
            out.append({"id": t["id"], "customer": t["customer_name"], "tier": t["plan_tier"], "subject": t["subject"], "body": t["body"], "channel": t["channel"],
                        "created_at": t["created_at"], "category": c, "confidence": conf, "source": src, "keywords": why, "priority": p, "score": s,
                        "reasons": [{"label": a, "points": b} for a, b in reasons], "team": team, "route_reason": rr, "incident": i[0], "incident_size": i[1],
                        "sla_minutes_left": round(rem), "breached": rem < 0, "reply": reply, "reply_source": rsrc,
                        "summary": (ai or {}).get("summary", ""), "sentiment": (ai or {}).get("sentiment"), "urgency": (ai or {}).get("urgency"), "language": (ai or {}).get("language", ""), "escalated": t["id"] in alerted})
        out.sort(key=lambda x: (x["priority"], -x["score"], x["created_at"]))
        return out

    def stats(self, out):
        cnt = lambda k: {v: sum(1 for x in out if x[k] == v) for v in sorted({x[k] for x in out})}
        incs = {}
        for x in out:
            if x["incident"]: incs.setdefault(x["incident"], {"id": x["incident"], "size": x["incident_size"], "title": x["subject"], "category": x["category"]})
        ai = sum(1 for x in out if x["source"] == "llm")
        return {"total": len(out), "by_priority": cnt("priority"), "by_category": cnt("category"), "by_team": cnt("team"), "breached": sum(1 for x in out if x["breached"]),
                "incidents": list(incs.values()), "llm": self.llm.enabled, "model": self.llm.model, "ai_triaged": ai,
                "learned_terms": self.db.q("SELECT COUNT(*) c FROM learned")[0]["c"], "corrections": self.db.q("SELECT COUNT(*) c FROM tickets WHERE override IS NOT NULL")[0]["c"]}
