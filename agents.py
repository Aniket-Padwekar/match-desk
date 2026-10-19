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
    if k == "score_after":
        e = next((x for x in ev if x["id"] == p["event_id"]), None)
        ok = bool(e) and e["type"] == "goal" and (e["score_home"], e["score_away"]) == (p["home"], p["away"])
        return ok, f'event #{p["event_id"]}: score {e["score_home"]}-{e["score_away"]}' if e else "no such event"
    if k == "why":
        w = why_result(m); ok = bool(w) and p["reason"] in [r["text"] for r in w["reasons"]]
        return ok, "recomputed from event log"
    if k == "injury":
        e = next((x for x in ev if x["id"] == p["event_id"]), None)
        ok = bool(e) and e["type"] == "injury_stoppage" and e["player"] == p["player"] and e["outcome"] == p["outcome"]
        return ok, f'event #{p["event_id"]}' if e else "no such event"
    if k == "tool":
        from ask import run_tool
        r = run_tool(m, p["tool"], p["args"]); return bool(r) and r["text"] == p["text"], "re-run on the event log"
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
    for k in key_moments(m):
        if k["kind"] == "goal":
            hh, aa = map(int, k["score"].split("-"))
            add("score_after", f'After {k["player"]}\'s goal for {k["team"]} in minute {k["minute"]+1} it was {hh}-{aa} ({meta["home"]} {hh}, {meta["away"]} {aa})',
                event_id=k["event_ids"][0], home=hh, away=aa)
    w = why_result(m)
    for r in (w or {}).get("reasons", []):
        add("why", r["text"], reason=r["text"])
    for e in [x for x in m["events"] if x["type"] == "injury_stoppage"]:
        tail = "was substituted because of the injury" if e["outcome"] == "substituted" else "carried on"
        add("injury", f'{e["player"]} ({e["team"]}) went down injured in minute {e["minute"]+1}; play was stopped for {e["duration_s"]} seconds and he {tail}',
            event_id=e["id"], player=e["player"], outcome=e["outcome"])
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
    for tm in (meta["home"], meta["away"]):
        first = tm.split()[0]
        if re.search(rf"\b{re.escape(first)}\b(?!\s+{re.escape(tm.split()[1])})", sentence["text"]):
            return False, f"shortened team name '{first}' (use '{tm}')", []
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
    def plan(self, m, q):
        from ask import MockPlanner; return MockPlanner().plan(m, q)
    def answer_write(self, question, facts, audience, lang):
        return {"sentences": [{"text": f["text"], "fact_ids": [f["id"]]} for f in facts]}
    def judge(self, items):
        """Offline stand-in for the LLM judge: supported only if the sentence shares most content words with its cited facts."""
        W = lambda t: {w for w in re.findall(r"[a-zäöüß0-9]+", t.lower()) if len(w) > 2}
        return [len(W(i["sentence"]) & W(" ".join(i["cited_facts"]))) >= 0.6 * max(1, len(W(i["sentence"]))) for i in items]
    def fix(self, sentence, facts_by_id, reason):
        f = facts_by_id[sentence["fact_ids"][0]] if sentence["fact_ids"] else None
        return None if f is None else {"text": f["text"] + ".", "fact_ids": [f["id"]]}

STYLE = {
 "fan": "Write like a friendly match report for someone who watched casually. Plain words. Never use the words 'expected goals' or 'xG'. Say 'chances worth 3.6 goals on average (a measure of how good the chances were)' the first time, then 'chance quality'. Tell the story: who scored when, who had the better of it, and why the result came out as it did. Max 7 short sentences.",
 "analyst": "Write for a stats-literate reader. Use the numbers, expected goals (xG), touches share and the 'why' facts. Precise and compact, no filler. Max 7 sentences.",
 "coach": "Write for a coach: what changed, why it mattered, what to take away. Focus on spells, finishing, goalkeeper impact and turning points. No stat dumps. Max 6 sentences."}

class AzureLLM:
    def __init__(self, endpoint, key, deployment):
        from openai import AzureOpenAI
        self.c = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version="2025-04-01-preview"); self.d = deployment
    def _chat(self, system, user):
        kw = dict(model=self.d, max_completion_tokens=6000, response_format={"type": "json_object"},
                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        try: r = self.c.chat.completions.create(reasoning_effort="low", **kw)
        except Exception: r = self.c.chat.completions.create(**kw)
        return json.loads(r.choices[0].message.content)
    def write(self, facts, audience, lang):
        sys = ("You are the Storyteller of a verified football match desk. Use ONLY the facts given. Every sentence must cite the fact ids it uses. "
               "Keep every sentence under 25 words and cite at most 3 facts per sentence; several short sentences beat one long one. Structure: (1) result, (2) the turning points using the score_after facts, (3) the reason the result came out that way using the 'why' facts, (4) one standout player. Always use full team names, never shortened. Never add a number, name, minute, or comparison that the cited facts do not state. Do not use interpretive words such as 'dominated', 'deserved', 'early', "
               "'better', 'more' unless a cited fact states the comparison with numbers. Prefer plain description over interpretation. "
               f"Style: {STYLE[audience]} Language: {lang}. "
               'Return JSON: {"headline":"...","sentences":[{"text":"...","fact_ids":[1,2]}]}')
        return self._chat(sys, json.dumps(facts, ensure_ascii=False))
    def plan(self, m, question):
        from ask import TOOL_SPECS
        me = m["meta"]
        sys = ("You turn a football question about ONE match into tool calls. " + TOOL_SPECS + f" The match is {me['home']} (home) vs {me['away']} (away). "
               'Return JSON: {"calls":[{"tool":"...","args":{...}}]} or {"unanswerable":"<short phrase, max 15 words, what is missing; never ask a question back>"}. At most 3 calls. Use the tools even if the question says "home team" or "away team".')
        r = self._chat(sys, question)
        return r["calls"] if r.get("calls") else {"unanswerable": r.get("unanswerable") or "no tool fits"}
    def answer_write(self, question, facts, audience, lang):
        sys = ("You answer a football question using ONLY the facts given. Cite the fact ids used in every sentence. Never add a number, name or comparison that the facts do not state; "
               "no causes or opinions unless a fact states them. Answer only what was asked; do NOT add sentences about what the facts leave out. "
               f"Style: {STYLE[audience]} Language: {lang}. Answer in 1-3 short sentences. "
               'Return JSON: {"sentences":[{"text":"...","fact_ids":[1]}]}')
        return self._chat(sys, json.dumps({"question": question, "facts": [{"id": f["id"], "text": f["text"]} for f in facts]}, ensure_ascii=False))
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

def det_headline(m):
    """Headline is built from the log, not written by the model, so it cannot be wrong."""
    me = m["meta"]; h, a = me["final_score"]["home"], me["final_score"]["away"]
    if h == a: return f'{me["home"]} {h}-{a} {me["away"]}: honours even'
    w, l = (me["home"], me["away"]) if h > a else (me["away"], me["home"])
    return f'{w} beat {l} {max(h,a)}-{min(h,a)}'

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
    return {"audience": audience, "language": lang, "headline": det_headline(m), "sentences": final, "trace": trace, "stats": st,
            "why": (case["why"] or {}).get("headline")}

def evaluate(n=30, err=0.25):
    from simulate import simulate
    t = dict(drafted=0, blocked=0, fixed=0, dropped=0, wrong_shown=0, shown=0)
    for s in range(1, n + 1):
        out = pipeline(simulate(s), MockLLM(err, seed=s)); st = out["stats"]
        t["drafted"] += st["drafted"]; t["blocked"] += st["blocked_first_pass"]; t["fixed"] += st["fixed"]; t["dropped"] += st["dropped"]
        t["shown"] += len(out["sentences"]); t["wrong_shown"] += sum(1 for x in out["sentences"] if x["_mutated"])
    t["first_pass_error_rate_%"] = round(100 * t["blocked"] / t["drafted"], 1); return t

def real_scorecard(llm, n_matches=8, seed0=100, verbose=True):
    """Plants known errors into sentences and measures how many the checker (rules + judge) catches.
    Also measures false blocks on sentences that are true by construction."""
    from simulate import simulate
    rng = random.Random(7); rows = []   # (kind, is_error, blocked, text)
    for sd in range(seed0, seed0 + n_matches):
        m = simulate(sd); case = analyst(m); facts = case["facts"]; fb = {f["id"]: f for f in facts}; me = m["meta"]
        cands = []   # (kind, is_error, text, ids)
        for f in facts:
            t = f["text"] + "."
            cands.append(("true_fact", False, t, [f["id"]]))
            nums = re.findall(r"\d+(?:\.\d+)?", f["text"])
            if nums:
                n = rng.choice(nums); bad = t.replace(n, str(round(float(n) + rng.choice([-2, -1, 1, 3]), 2)), 1)
                cands.append(("wrong_number", True, bad, [f["id"]]))
            if me["home"] in f["text"] and me["away"] not in f["text"]:
                cands.append(("wrong_team", True, t.replace(me["home"], me["away"]), [f["id"]]))
            cands.append(("invented_cause", True, t[:-1] + " because they pressed much higher up the pitch.", [f["id"]]))
            other = rng.choice([g for g in facts if g["id"] != f["id"]])
            cands.append(("wrong_citation", True, t, [other["id"]]))
        hs, as_ = team_stat(m["events"], "home", "shots"), team_stat(m["events"], "away", "shots")
        ids = {c["kind"] + c["params"].get("side", ""): f["id"] for f in facts for c in [f["claim"]] if c["kind"] == "team_stat" and c["params"].get("stat") == "shots"}
        sh = [f for f in facts if f["claim"]["kind"] == "team_stat" and f["claim"]["params"].get("stat") == "shots"]
        if len(sh) == 2 and hs != as_:
            more, less = (me["home"], me["away"]) if hs > as_ else (me["away"], me["home"])
            cids = [f["id"] for f in sh]
            cands.append(("true_comparison", False, f"{more} had more shots than {less}.", cids))
            cands.append(("flipped_comparison", True, f"{less} had more shots than {more}.", cids))
        # rules first, then judge on whatever the rules let through
        items, idx = [], []
        res = []
        for kind, err, text, ids_ in cands:
            ok, why, _ = checker(m, {"text": text, "fact_ids": ids_}, fb)
            res.append([kind, err, not ok, text])
            if ok: idx.append(len(res) - 1); items.append({"i": len(items), "sentence": text, "cited_facts": [fb[x]["text"] for x in ids_]})
        for a in range(0, len(items), 20):
            chunk = items[a:a + 20]
            for it, j in zip(chunk, llm.judge([dict(x, i=k) for k, x in enumerate(chunk)])):
                res[idx[it["i"]]][2] = not j
        rows += res
        if verbose: print(f"match {sd}: {len(cands)} test sentences done")
    out = {}
    for kind in sorted({r[0] for r in rows}):
        sub = [r for r in rows if r[0] == kind]; out[kind] = (sum(r[2] for r in sub), len(sub))
    errs = [r for r in rows if r[1]]; trues = [r for r in rows if not r[1]]
    summary = {"planted_errors": len(errs), "caught": sum(r[2] for r in errs), "catch_rate_%": round(100 * sum(r[2] for r in errs) / len(errs), 1),
               "true_sentences": len(trues), "wrongly_blocked": sum(r[2] for r in trues), "false_block_rate_%": round(100 * sum(r[2] for r in trues) / len(trues), 1),
               "by_kind(blocked,total)": out,
               "missed_examples": [r[3] for r in errs if not r[2]][:8]}
    return summary

if __name__ == "__main__":
    from simulate import simulate
    m = simulate(24); case = analyst(m)
    for f in case["facts"][-4:]: print(f["id"], f["text"], verify(f["claim"], m))
    # regression: the exact false sentence the real model produced in the first run
    fb = {f["id"]: f for f in case["facts"]}
    bad = {"text": f'{m["meta"]["home"]} hatten deutlich mehr Ballbesitz mit 47% der Ballkontakte.', "fact_ids": [13]}
    print("false-possession test ->", checker(m, bad, fb)[:2])
    bad2 = {"text": "Der Torwart machte fünf Paraden.", "fact_ids": [8]}
    print("spelled-number test ->", checker(m, bad2, fb)[:2])
    print(evaluate())
