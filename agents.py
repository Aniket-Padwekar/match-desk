"""Agent layer: Storyteller -> FactChecker -> Editor loop with a shared case file and a trace.
Roles are separate agents; the checker never trusts the writer: it re-derives every fact from the raw event log."""
import json, re, random
from engine import make_claims, verify, summarize, verdict, key_moments
from insight import why_result

# ---------------- LLM backends ----------------
class MockLLM:
    """Stand-in model for offline testing. err_rate simulates hallucinated numbers / wrong citations."""
    def __init__(self, err_rate=0.25, seed=0): self.err, self.rng = err_rate, random.Random(seed)
    def write(self, facts, audience, lang):
        out = []
        for f in facts:
            text, ids = f["text"], [f["id"]]
            mutated = False
            if self.rng.random() < self.err:
                mutated = True
                nums = re.findall(r"\d+(?:\.\d+)?", text)
                if nums and self.rng.random() < 0.7:
                    n = self.rng.choice(nums); text = text.replace(n, str(round(float(n) + self.rng.choice([-3, -1, 2, 5]), 2)), 1)
                else: ids = [self.rng.choice([g for g in facts if g["id"] != f["id"]])["id"]]
            out.append({"text": text + ".", "fact_ids": ids, "_mutated": mutated})
        return out
    def fix(self, sentence, facts_by_id, reason):
        f = facts_by_id[sentence["fact_ids"][0]] if sentence["fact_ids"] else None
        return None if f is None else {"text": f["text"] + ".", "fact_ids": [f["id"]]}

class AzureLLM:
    """Real model on Azure (works in Colab). Needs endpoint, key, deployment."""
    def __init__(self, endpoint, key, deployment):
        from openai import AzureOpenAI
        self.c = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version="2025-04-01-preview"); self.d = deployment
    def _chat(self, system, user):
        kw = dict(model=self.d, max_completion_tokens=2500, response_format={"type": "json_object"},
                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        try: r = self.c.chat.completions.create(reasoning_effort="low", **kw)
        except Exception: r = self.c.chat.completions.create(**kw)
        return json.loads(r.choices[0].message.content)
    def write(self, facts, audience, lang):
        style = {"fan": "plain words, short, no jargon, one idea per sentence",
                 "analyst": "precise, use the numbers, mention expected goals (xG)",
                 "coach": "decision-focused: what changed and why it matters, no stat dumps"}[audience]
        sys = ("You write football match recaps. Use ONLY the facts given. Every sentence must cite the fact ids it uses. "
               "Never add a number, name or minute that is not in the cited facts. "
               f"Audience style: {style}. Language: {lang}. "
               'Return JSON: {"sentences":[{"text":"...","fact_ids":[1,2]}]}')
        return self._chat(sys, json.dumps(facts))["sentences"]
    def fix(self, sentence, facts_by_id, reason):
        sys = ("Rewrite ONE sentence so it is fully supported by the allowed facts, or return null if it cannot be. "
               'Return JSON: {"sentence": {"text":"...","fact_ids":[...]} or null}')
        allowed = [facts_by_id[i] for i in sentence["fact_ids"] if i in facts_by_id]
        return self._chat(sys, json.dumps({"bad": sentence, "reason": reason, "allowed_facts": allowed}))["sentence"]

# ---------------- agents ----------------
def analyst(m):
    """StatsAnalyst: deterministic. Builds the case file of facts (checkable claims) + extra context."""
    claims = make_claims(m)
    facts = [{"id": c["id"], "text": c["text"], "claim": c} for c in claims]
    return {"facts": facts, "verdict": verdict(m), "why": why_result(m), "moments": key_moments(m)}

NUM = re.compile(r"\d+(?:\.\d+)?")
def allowed_numbers(f):
    c = f["claim"]; p = c["params"]; nums = set(NUM.findall(f["text"]))
    return nums

def checker(m, sentence, facts_by_id):
    """FactChecker: returns (ok, reason, receipts). Independent of the writer."""
    meta = m["meta"]; ids = sentence.get("fact_ids") or []
    if not ids or any(i not in facts_by_id for i in ids): return False, "no valid fact cited", []
    receipts = []
    for i in ids:
        ok, why = verify(facts_by_id[i]["claim"], m)
        if not ok: return False, f"fact {i} fails check: {why}", []
        receipts.append(why)
    # entity check: every team/player named in the sentence must appear in a cited fact
    ents = [meta["home"], meta["away"]] + [p["name"] for sd in ("home", "away") for p in m["meta"]["lineups"][sd]["players"] + m["meta"]["lineups"][sd]["bench"]]
    cited_text = " ".join(facts_by_id[i]["text"] for i in ids)
    for e in ents:
        if e in sentence["text"] and e not in cited_text: return False, f"{e} is not in the cited facts", []
    allowed = set().union(*[allowed_numbers(facts_by_id[i]) for i in ids])
    stray = [n for n in NUM.findall(sentence["text"]) if n not in allowed]
    if stray: return False, f"number(s) {stray} not in cited facts", []
    return True, "verified", receipts

def pipeline(m, llm, audience="fan", lang="English", max_fix=1):
    case = analyst(m); facts = case["facts"]; fb = {f["id"]: f for f in facts}
    trace = [{"agent": "StatsAnalyst", "event": f'{len(facts)} facts built from the event log'}]
    draft = llm.write([{"id": f["id"], "text": f["text"]} for f in facts], audience, lang)
    trace.append({"agent": "Storyteller", "event": f"drafted {len(draft)} sentences"})
    final, blocked_first, fixed, dropped = [], 0, 0, 0
    for s in draft:
        ok, reason, rec = checker(m, s, fb)
        if not ok:
            blocked_first += 1; trace.append({"agent": "FactChecker", "event": f"blocked: {reason}"})
            for _ in range(max_fix):
                s2 = llm.fix(s, fb, reason)
                if s2 and checker(m, s2, fb)[0]:
                    s2["_mutated"] = False; s = s2; ok, reason, rec = checker(m, s, fb); fixed += 1
                    trace.append({"agent": "Editor", "event": "rewrote sentence; re-check passed"}); break
            else: pass
            if not ok: dropped += 1; trace.append({"agent": "Editor", "event": "dropped unsupported sentence"}); continue
        final.append({"text": s["text"], "fact_ids": s["fact_ids"], "status": "verified", "receipts": rec,
                      "_mutated": s.get("_mutated", False)})
    return {"audience": audience, "language": lang, "sentences": final, "trace": trace,
            "stats": {"drafted": len(draft), "blocked_first_pass": blocked_first, "fixed": fixed, "dropped": dropped}}

def evaluate(n=30, err=0.25):
    from simulate import simulate
    tot = dict(drafted=0, blocked=0, fixed=0, dropped=0, wrong_shown=0, shown=0)
    for s in range(1, n + 1):
        m = simulate(s); out = pipeline(m, MockLLM(err, seed=s))
        st = out["stats"]; tot["drafted"] += st["drafted"]; tot["blocked"] += st["blocked_first_pass"]
        tot["fixed"] += st["fixed"]; tot["dropped"] += st["dropped"]
        tot["shown"] += len(out["sentences"]); tot["wrong_shown"] += sum(1 for x in out["sentences"] if x["_mutated"])
    tot["first_pass_error_rate_%"] = round(100 * tot["blocked"] / tot["drafted"], 1)
    tot["errors_shown_to_reader"] = tot["wrong_shown"]
    return tot

if __name__ == "__main__":
    from simulate import simulate
    m = simulate(3); out = pipeline(m, MockLLM(0.3, 1))
    for s in out["sentences"][:5]: print("-", s["text"], s["fact_ids"], s["receipts"])
    print(out["stats"]); print(out["trace"][:6]); print(evaluate())
