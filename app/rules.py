"""Deterministic triage rules: classify, cluster incidents, score priority, route, draft. No I/O, no framework."""
import difflib, itertools, re

STOP = set("the a an is are was were to of and or in on for my our we i you it this that with not no be have has can please hi hello hey thanks thank team your have from but".split())
OUTAGE = ["down","outage","all users","everyone","production","urgent","asap","data loss","lost data","not loading","500","critical","emergency","breach","blocked","band ho gaya"]
ANGRY = ["worst","unacceptable","furious","angry","ridiculous","cancel","legal","scam","useless","terrible","garbage","third time","still not","nobody replies","pathetic"]
TIER = {"free": 0, "pro": 1, "enterprise": 2}
SLA = {"P1": 60, "P2": 240, "P3": 1440, "P4": 4320}  # minutes

def toks(t): return re.findall(r"[a-z0-9']+", (t or "").lower())
def hits(text, words, kws):
    """Keyword hits: phrases by regex, single words exact or fuzzy (typo tolerant)."""
    found = []
    for k in kws:
        k = k.lower()
        if not k.isalnum():
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", text): found.append(k)
        elif k in words: found.append(k)
        elif len(k) >= 5 and any(fuzzy(k, w) for w in words): found.append(k)
    return found

def fuzzy(k, w):
    """Typo match ('invocie' ~ 'invoice') without matching a different word that merely contains the keyword ('blocked' !~ 'locked')."""
    return w[:1] == k[:1] and abs(len(w) - len(k)) <= 2 and difflib.SequenceMatcher(None, k, w).ratio() >= 0.84

def classify(t, cats, learned=None):
    learned = learned or {}
    subj, body = t["subject"].lower(), t["body"].lower()
    sw, bw = list(set(toks(subj))), list(set(toks(body)))
    scores, why = {}, {}
    for c, v in cats.items():
        hs, hb = hits(subj, sw, v["keywords"]), hits(body, bw, v["keywords"])
        s = 2 * len(hs) + len(set(hb) - set(hs))
        s += sum(min(learned.get(c, {}).get(w, 0), 3) * 0.5 for w in set(sw + bw))
        if s > 0: scores[c], why[c] = s, sorted(set(hs + hb))
    if not scores: return "other", 0.3, []
    best = max(scores, key=scores.get)
    return best, round(scores[best] / sum(scores.values()), 2), why[best]

def clusters(ts):
    """Group near-duplicate tickets (Jaccard >= 0.3 within 45 min) with union-find."""
    sets = [set(w for w in toks(t["subject"] + " " + t["body"]) if w not in STOP and len(w) > 2) for t in ts]
    par = list(range(len(ts)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i, j in itertools.combinations(range(len(ts)), 2):
        a, b = sets[i], sets[j]
        if a and b and abs((ts[i]["_dt"] - ts[j]["_dt"]).total_seconds()) <= 2700 and len(a & b) / len(a | b) >= 0.3:
            par[f(i)] = f(j)
    g = {}
    for i in range(len(ts)): g.setdefault(f(i), []).append(i)
    return list(g.values())

def priority(t, cat, cats, cluster, repeat, ai=None):
    text = (t["subject"] + " " + t["body"]).lower(); words = list(set(toks(text))); r = []
    if cats.get(cat, {}).get("base"): r.append((f"Category: {cat.replace('_', ' ')}", cats[cat]["base"]))
    o = hits(text, words, OUTAGE)
    if o: r.append(("Outage or urgency words: " + ", ".join(o[:3]), min(3, len(o) + 1)))
    a, ex = hits(text, words, ANGRY), text.count("!")
    if a or ex >= 3: r.append(("Angry tone", 2 if len(a) > 1 or ex >= 3 else 1))
    elif ai and ai.get("sentiment", 0) <= -1: r.append(("Negative tone (AI)", 2 if ai["sentiment"] <= -2 else 1))
    if ai and ai.get("urgency", 0) >= 4: r.append((f"AI urgency {ai['urgency']}/5", 2))
    if TIER.get(t["plan_tier"], 0): r.append((f"{t['plan_tier']} plan", TIER[t["plan_tier"]]))
    if t["channel"] == "twitter": r.append(("Public channel (twitter)", 1))
    if repeat: r.append((f"{repeat} earlier ticket(s) from this customer", 1))
    if cluster >= 4: r.append((f"Part of an incident ({cluster} similar tickets)", 2))
    s = sum(p for _, p in r)
    return ("P1" if s >= 8 else "P2" if s >= 5 else "P3" if s >= 3 else "P4"), s, r

def route(cat, p, t, cats):
    team = cats.get(cat, {}).get("team", "Support L1")
    reason = f"{cat.replace('_', ' ').capitalize()} tickets go to {team}"
    if t["plan_tier"] == "enterprise" and p in ("P1", "P2"):
        reason += f"; enterprise {p}, notify the account manager"
    return team, reason

def draft(t, kb, incident):
    first = t["customer_name"].split()[0]
    if incident:
        body = "We're aware of an issue affecting several customers and our engineers are investigating. We'll update you as soon as it's resolved."
    else:
        words = list(set(toks(t["subject"] + " " + t["body"]))); text = (t["subject"] + " " + t["body"]).lower()
        best = max(kb, key=lambda k: len(hits(text, words, k["keywords"])))
        body = best["answer"] if hits(text, words, best["keywords"]) else "Thanks for reaching out. A teammate is reviewing your message and will reply shortly."
    return f"Hi {first},\n\n{body}\n\nIf this doesn't solve it, just reply here.\n\nYottaflex Support"

