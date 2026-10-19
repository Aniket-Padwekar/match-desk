"""Agent layer: StatsAnalyst -> Storyteller -> FactChecker (rules) -> Judge (meaning) -> Editor, with a trace.
The checker never trusts the writer: it re-derives every fact from the raw event log."""
import json, re, random
from engine import make_claims, verify as verify_basic, summarize, verdict, key_moments, team_stat, possession, ev_of
from insight import why_result, ratings

# ---------------- number words (EN/DE) so spelled-out numbers cannot slip past the checker ----------------
WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12}
NUM = re.compile(r"\d+(?:[.,]\d+)?")
def numbers_in(text):
    ns = {n.replace(",", ".") for n in NUM.findall(text)}
    for w in re.findall(r"[A-Za-zäöüÄÖÜß]+", text.lower()):
        if w in WORDS: ns.add(str(WORDS[w]))
    return ns

# ---------------- extra checkable facts (verified by recomputing from the event log) ----------------
def verify(claim, m):
    k, p, ev = claim["kind"], claim["params"], m["events"]
    if k == "rating":
        r = ratings(m).get(p["pid"]); ok = bool(r) and abs(r["rating"] - p["value"]) < 0.05
        return ok, f'recomputed rating {r["rating"] if r else None}'
    if k == "spell":
        lo, hi, side = p["lo"], p["hi"], p["side"]
        other = "away" if side == "home" else "home"
        xs = lambda sd: sum(e["xg"] for e in ev if e["type"] == "shot" and e["side"] == sd and lo <= e["minute"] < hi)
        poss = possession(ev, side, lo, hi)
        return abs(poss - p["possession"]) <= 1 and abs((xs(side) - xs(other)) - p["xg_diff"]) <= 0.05, f"touches {poss}%"
    if k == "margin":
        h, a = team_stat(ev, "home", "goals"), team_stat(ev, "away", "goals")
        return (h - a) == p["diff"], f"goal difference {h - a}"
    return verify_basic(claim, m)

def analyst(m):
    """StatsAnalyst: deterministic. Builds the case file of checkable facts."""
    claims = make_claims(m); meta = m["meta"]; S = summarize(m); v = verdict(m)
    def add(kind, text, **p): claims.append({"id": len(claims) + 1, "kind": kind, "text": text, "params": p})
    h, a = S["home"]["goals"], S["away"]["goals"]
    if h != a:
        w = meta["home"] if h > a else meta["away"]; l = meta["away"] if h > a else meta["home"]
        add("margin", f"{w} won by {abs(h - a)} goal(s) against {l}", diff=h - a)
    else: add("margin", "The match ended level", diff=0)
    for k in key_moments(m):
        if k["kind"] == "spell":
            add("spell", f'From minute {k["minute"]+1} to {k["to"]} {k["team"]} had {k["possession"]:.0f}% of the touches and led the chances by {k["xg_diff"]} expected goals',
                side=k["side"], lo=k["minute"], hi=k["to"], possession=k["possession"], xg_diff=k["xg_diff"]); break
    rt = ratings(m)
    if rt:
        top = max(rt.items(), key=lambda kv: kv[1]["rating"]); pid, r = top
        add("rating", f'{r["player"]} had the highest rating, {r["rating"]}, on {r["touches"]} touches', pid=pid, value=r["rating"])
    facts = [{"id": c["id"], "text": c["text"], "claim": c} for c in claims]
    return {"facts": facts, "verdict": v, "why": why_result(m), "moments": key_moments(m)}

def checker(m, sentence, facts_by_id):
    """FactChecker (rules): citations, numbers (digits + number words), names, comparison words."""
    meta = m["meta"]; ids = sentence.get("fact_ids") or []
    if not ids or any(i not in facts_by_id for i in ids): return False, "no valid fact cited", []
    receipts = []
    for i in ids:
        ok, why = verify(facts_by_id[i]["claim"], m)
        if not ok: return False, f"fact {i} fails check: {why}", []
        receipts.append(why)
    ents = [meta["home"], meta["away"]] + [p["name"] for sd in ("home", "away") for p in meta["lineups"][sd]["players"] + meta["lineups"][sd]["bench"]]
    cited_text = " ".join(facts_by_id[i]["text"] for i in ids)
    for e in ents:
        if e in sentence["text"] and e not in cited_text: return False, f"{e} is not in the cited facts", []
    allowed = set().union(*[numbers_in(facts_by_id[i]["text"]) for i in ids])
    stray = [n for n in numbers_in(sentence["text"]) if n not in allowed]
    if stray: return False, f"number(s) {stray} not in cited facts", []
    # comparison words about possession must agree with the cited possession value
    t = sentence["text"].lower()
    pos_facts = [facts_by_id[i]["claim"] for i in ids if facts_by_id[i]["claim"]["kind"] == "possession"]
    if pos_facts and re.search(r"more possession|mehr ballbesitz|ballbesitz.*deutlich|dominated possession|controlled the ball|larger share", t):
        if pos_facts[0]["params"]["value"] <= 50: return False, "says more possession, but cited share is 50% or less", []
    return True, "verified", receipts

# ---------------- LLM backends ----------------
class MockLLM:
    def __init__(self, err_rate=0.25, seed=0): self.err, self.rng = err_rate, random.Random(seed)
    def write(self, facts, audience, lang):
        out = []
        for f in facts:
            text, ids, mutated = f["text"], [f["id"]], False
            if self.rng.random() < self.err:
                mutated = True; nums = re.findall(r"\d+(?:\.\d+)?", text)
                if nums and self.rng.random() < 0.7:
                    n = self.rng.choice(nums); text = text.replace(n, str(round(float(n) + self.rng.choice([-3, -1, 2, 5]), 2)), 1)
                else: ids = [self.rng.choice([g for g in facts if g["id"] != f["id"]])["id"]]
            out.append({"text": text + ".", "fact_ids": ids, "_mutated": mutated})
        return {"headline": "", "sentences": out}
    def judge(self, items):
        """Offline stand-in for the LLM judge: supported only if the sentence shares most content words with its cited facts."""
        W = lambda t: {w for w in re.findall(r"[a-zäöüß0-9]+", t.lower()) if len(w) > 2}
        return [len(W(i["sentence"]) & W(" ".join(i["cited_facts"]))) >= 0.6 * max(1, len(W(i["sentence"]))) for i in items]
    def fix(self, sentence, facts_by_id, reason):
        f = facts_by_id[sentence["fact_ids"][0]] if sentence["fact_ids"] else None
        return None if f is None else {"text": f["text"] + ".", "fact_ids": [f["id"]]}

STYLE = {
 "fan": "Write like a friendly match report for someone who watched casually. Plain words. NEVER say 'expected goals' or 'xG' on its own: say 'the quality of chances' and explain in a few words. Tell the story: who scored when, who had the better of it, and why the result came out as it did. Max 6 short sentences.",
 "analyst": "Write for a stats-literate reader. Use the numbers, expected goals (xG), touches share and the 'why' facts. Precise and compact, no filler. Max 7 sentences.",
 "coach": "Write for a coach: what changed, why it mattered, what to take away. Focus on spells, finishing, goalkeeper impact and turning points. No stat dumps. Max 6 sentences."}

class AzureLLM:
    def __init__(self, endpoint, key, deployment):
        from openai import AzureOpenAI
        self.c = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version="2025-04-01-preview"); self.d = deployment
    def _chat(self, system, user):
        kw = dict(model=self.d, max_completion_tokens=3000, response_format={"type": "json_object"},
                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        try: r = self.c.chat.completions.create(reasoning_effort="low", **kw)
        except Exception: r = self.c.chat.completions.create(**kw)
        return json.loads(r.choices[0].message.content)
    def write(self, facts, audience, lang):
        sys = ("You are the Storyteller of a verified football match desk. Use ONLY the facts given. Every sentence must cite the fact ids it uses. "
               "Never add a number, name, minute, or comparison that the cited facts do not state. Do not use interpretive words such as 'dominated', 'deserved', 'early', "
               "'better', 'more' unless a cited fact states the comparison with numbers. Prefer plain description over interpretation. "
               f"Style: {STYLE[audience]} Language: {lang}. "
               'Return JSON: {"headline":"...","sentences":[{"text":"...","fact_ids":[1,2]}]}')
        return self._chat(sys, json.dumps(facts, ensure_ascii=False))
    def judge(self, items):
        sys = ("You are a strict football fact judge. For each item, decide whether the sentence is FULLY supported by its cited facts: "
               "every claim, comparison (more/less/better), time word (early/late) and implied cause must be stated or directly follow from the facts. "
               'Return JSON: {"verdicts":[{"i":0,"supported":true,"problem":""}]}')
        r = self._chat(sys, json.dumps(items, ensure_ascii=False))["verdicts"]
        by = {v["i"]: v["supported"] for v in r}; self.last_problems = {v["i"]: v.get("problem", "") for v in r}
        return [bool(by.get(i, False)) for i in range(len(items))]
    def fix(self, sentence, facts_by_id, reason):
        sys = ("Rewrite ONE sentence so it is fully supported by the allowed facts using only plain description, or return null if it cannot be. "
               'Return JSON: {"sentence": {"text":"...","fact_ids":[...]} or null}')
        allowed = [{"id": i, "text": facts_by_id[i]["text"]} for i in sentence["fact_ids"] if i in facts_by_id]
        return self._chat(sys, json.dumps({"bad": sentence["text"], "reason": reason, "allowed_facts": allowed}, ensure_ascii=False))["sentence"]

# ---------------- orchestration ----------------
def pipeline(m, llm, audience="fan", lang="English", max_fix=1):
    case = analyst(m); facts = case["facts"]; fb = {f["id"]: f for f in facts}
    trace = [{"agent": "StatsAnalyst", "event": f'{len(facts)} facts built from the event log'}]
    w = llm.write([{"id": f["id"], "text": f["text"]} for f in facts], audience, lang)
    draft, headline = w["sentences"], w.get("headline", "")
    trace.append({"agent": "Storyteller", "event": f"drafted {len(draft)} sentences"})
    rules = [checker(m, s, fb) for s in draft]
    jitems = [{"i": i, "sentence": s["text"], "cited_facts": [fb[x]["text"] for x in s["fact_ids"] if x in fb]} for i, s in enumerate(draft)]
    judged = llm.judge(jitems) if jitems else []
    final, st = [], dict(drafted=len(draft), blocked_by_rules=0, blocked_by_judge=0, fixed=0, dropped=0)
    for i, s in enumerate(draft):
        ok, reason, rec = rules[i]
        if ok and not judged[i]:
            ok, reason = False, "judge: " + (getattr(llm, "last_problems", {}).get(i) or "not fully supported by cited facts"); st["blocked_by_judge"] += 1
        elif not ok: st["blocked_by_rules"] += 1
        if not ok:
            trace.append({"agent": "Judge" if reason.startswith("judge") else "FactChecker", "event": f"blocked: {reason}"})
            for _ in range(max_fix):
                s2 = llm.fix(s, fb, reason)
                if s2:
                    ok2, r2, rec2 = checker(m, s2, fb)
                    j2 = llm.judge([{"i": 0, "sentence": s2["text"], "cited_facts": [fb[x]["text"] for x in s2["fact_ids"] if x in fb]}])[0] if ok2 else False
                    if ok2 and j2: s2["_mutated"] = False; s, ok, rec = s2, True, rec2; st["fixed"] += 1; trace.append({"agent": "Editor", "event": "rewrote sentence; re-check passed"}); break
            if not ok: st["dropped"] += 1; trace.append({"agent": "Editor", "event": "dropped unsupported sentence"}); continue
        final.append({"text": s["text"], "fact_ids": s["fact_ids"], "status": "verified", "receipts": rec, "_mutated": s.get("_mutated", False)})
    st["blocked_first_pass"] = st["blocked_by_rules"] + st["blocked_by_judge"]
    return {"audience": audience, "language": lang, "headline": headline, "sentences": final, "trace": trace, "stats": st,
            "why": (case["why"] or {}).get("headline")}

def evaluate(n=30, err=0.25):
    from simulate import simulate
    t = dict(drafted=0, blocked=0, fixed=0, dropped=0, wrong_shown=0, shown=0)
    for s in range(1, n + 1):
        out = pipeline(simulate(s), MockLLM(err, seed=s)); st = out["stats"]
        t["drafted"] += st["drafted"]; t["blocked"] += st["blocked_first_pass"]; t["fixed"] += st["fixed"]; t["dropped"] += st["dropped"]
        t["shown"] += len(out["sentences"]); t["wrong_shown"] += sum(1 for x in out["sentences"] if x["_mutated"])
    t["first_pass_error_rate_%"] = round(100 * t["blocked"] / t["drafted"], 1); return t

if __name__ == "__main__":
    from simulate import simulate
    m = simulate(24); case = analyst(m)
    for f in case["facts"][-4:]: print(f["id"], f["text"], verify(f["claim"], m))
    # regression: the exact false sentence the real model produced in the first run
    fb = {f["id"]: f for f in case["facts"]}
    bad = {"text": "Rhein Rangers hatten deutlich mehr Ballbesitz mit 47% der Ballkontakte.", "fact_ids": [13]}
    print("false-possession test ->", checker(m, bad, fb)[:2])
    bad2 = {"text": "Der Torwart machte fünf Paraden.", "fact_ids": [8]}
    print("spelled-number test ->", checker(m, bad2, fb)[:2])
    print(evaluate())
