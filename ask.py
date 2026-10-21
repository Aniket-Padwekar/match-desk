"""Ask the Match: a question is turned into calls to a small set of deterministic tools over the event log.
The model never reads raw events and never invents numbers: it plans which tools to call, then explains what the
tools returned. Every sentence is re-checked (rules + judge) and carries receipts. If the tools cannot answer,
the answer is a plain 'the data cannot tell', written by code, not by the model."""
import json, re
from collections import Counter
from insight import ratings, explain_rating, why_result
from engine import key_moments, team_stat

STATS = {"shots": ["shot"], "goals": ["goal"], "passes": ["pass"], "tackles": ["tackle"], "interceptions": ["interception"], "fouls": ["foul"],
         "yellow cards": ["yellow_card"], "corners": ["corner"], "saves": ["save"], "dribbles": ["dribble"], "duels": ["duel"], "pressures": ["pressure"]}

TOOL_SPECS = """Tools (call with JSON):
- score_timeline() : every goal with minute, scorer and running score
- team_stat(side, stat, from_min, to_min) : side is 'home' or 'away'; stat is one of %s; from_min/to_min optional (match minutes 1-90+)
- player_stat(player, stat) : counts for one named player (full or last name); stat one of %s, or 'xg'
- top_players(stat, n) : the n players with the most of a stat (both teams)
- top_rated(n) : the n highest-rated players in the match, with why the best one scored so well
- rating(player) : the published rating formula applied to one player, with the biggest contributors
- why_result() : the reasons the result did or did not match the chances
- injuries() : injury stoppages (who, minute, how long play stopped, whether he was substituted off)
- substitutions() : every substitution with the reason recorded (injury or tactical)
- lineup_info(team) : players and positions of a team
- formation(team) : the starting shape (defenders-midfielders-forwards) read from the listed starting positions
If the question needs something the event log does not contain (changes of shape during play, tactics, instructions, injuries, fitness, intentions, opinions, players' speed or distance, anything about other matches or real teams), answer {"unanswerable": "<what is missing>"}.""" % (list(STATS), list(STATS))

def _players(m):
    out = []
    for sd in ("home", "away"):
        for p in m["meta"]["lineups"][sd]["players"] + m["meta"]["lineups"][sd]["bench"]:
            out.append((p["id"], p["name"], sd, p["pos"]))
    return out

def _find(m, q):
    q = q.lower().strip(); P = _players(m)
    hit = [p for p in P if p[1].lower() == q] or [p for p in P if q and q in p[1].lower()]
    return hit

def _window(e, lo, hi): return (lo is None or e["minute"] >= lo - 1) and (hi is None or e["minute"] < hi)

def _side_of(me, team):
    t = (team or "").lower().strip()
    if not t: return None
    if t in ("home", "home team", "the home team"): return "home"
    if t in ("away", "away team", "the away team", "visitors"): return "away"
    h, a = me["home"].lower(), me["away"].lower()
    if t in h or h in t: return "home"
    if t in a or a in t: return "away"
    if "home" in t: return "home"
    if "away" in t: return "away"
    return None

def run_tool(m, tool, args):
    """Returns {"text": str, "receipts": [event ids]} or None if the tool cannot answer."""
    ev, me = m["events"], m["meta"]; args = args or {}
    side_name = lambda s: me["home"] if s == "home" else me["away"]
    lab = lambda s: f'{side_name(s)} ({s} team)'
    if tool == "score_timeline":
        gs = [e for e in ev if e["type"] == "goal"]
        if not gs: return {"text": "No goals were scored.", "receipts": []}
        return {"text": "Goals: " + "; ".join(f'{e["player"]} for {side_name(e["side"])} in minute {e["minute"]+1} ({e["score_home"]}-{e["score_away"]})' for e in gs) + ".",
                "receipts": [e["id"] for e in gs]}
    if tool == "team_stat":
        side, stat = args.get("side"), args.get("stat")
        def _n(v):
            try: return int(float(v))
            except (TypeError, ValueError): return None
        lo, hi = _n(args.get("from_min")), _n(args.get("to_min"))
        if side not in ("home", "away") or stat not in STATS: return None
        hits = [e for e in ev if e["side"] == side and e["type"] in STATS[stat] and _window(e, lo, hi)]
        win = f' between minute {lo} and {hi}' if lo and hi else (f' from minute {lo} onwards' if lo else (f' up to minute {hi}' if hi else ''))
        return {"text": f'{lab(side)} had {len(hits)} {stat}{win}.', "receipts": [e["id"] for e in hits][:15]}
    if tool == "player_stat":
        hit = _find(m, args.get("player", ""))
        if not hit: return None
        if len(hit) > 1: return {"text": "Several players match '" + args["player"] + "': " + ", ".join(f"{p[1]} ({side_name(p[2])})" for p in hit) + ".", "receipts": []}
        pid, name, sd, pos = hit[0]; stat = args.get("stat")
        mine = [e for e in ev if e.get("player_id") == pid]
        if stat == "xg":
            sh = [e for e in mine if e["type"] == "shot"]
            return {"text": f'{name} ({side_name(sd)}) had {len(sh)} shots worth {round(sum(e["xg"] for e in sh),2)} expected goals.', "receipts": [e["id"] for e in sh]}
        if stat not in STATS: return None
        hits = [e for e in mine if e["type"] in STATS[stat]]
        return {"text": f'{name} ({side_name(sd)}) had {len(hits)} {stat}.', "receipts": [e["id"] for e in hits][:15]}
    if tool == "top_players":
        stat = args.get("stat"); n = int(args.get("n", 3) or 3)
        if stat not in STATS: return None
        c = Counter(e["player"] for e in ev if e["type"] in STATS[stat] and e.get("player"))
        if not c: return {"text": f"Nobody recorded any {stat}.", "receipts": []}
        top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
        cut = top[min(n, len(top)) - 1][1]; top = [t for t in top if t[1] >= cut][:max(n, 1)]
        lead = {p for p, _ in top}
        return {"text": f'Most {stat}: ' + ", ".join(f"{p} {k}" for p, k in top) + ".",
                "receipts": [e["id"] for e in ev if e["type"] in STATS[stat] and e.get("player") in lead][:15]}
    if tool == "top_rated":
        R = ratings(m); n = int(args.get("n", 3) or 3)
        best = sorted(R.items(), key=lambda kv: -kv[1]["rating"])[:max(n, 1)]
        pid, r0 = best[0]; ex = explain_rating(m, pid)
        return {"text": "Highest rated: " + ", ".join(f'{r["player"]} {r["rating"]}' for _, r in best) + ". " + ex["text"], "receipts": ex["receipts"]}
    if tool == "rating":
        hit = _find(m, args.get("player", ""))
        if len(hit) != 1: return None
        r = explain_rating(m, hit[0][0]); return {"text": r["text"], "receipts": r["receipts"]}
    if tool == "why_result":
        w = why_result(m)
        if not w:   # result matched the chances: state the plain comparison, no cause claimed
            xg = {sd: team_stat(ev, sd, "xg") for sd in ("home", "away")}; sh = {sd: team_stat(ev, sd, "shots") for sd in ("home", "away")}
            hg, ag = me["final_score"]["home"], me["final_score"]["away"]
            txt = f'{me["home"]} {hg}-{ag} {me["away"]}. Chance quality was {xg["home"]} for {me["home"]} and {xg["away"]} for {me["away"]} (expected goals), with {sh["home"]} and {sh["away"]} shots. No unusual gap between the chances and the result was found.'
            return {"text": txt, "receipts": [e["id"] for e in ev if e["type"] == "goal"]}
        return {"text": w["headline"] + " " + " ".join(r["text"] for r in w["reasons"]), "receipts": [i for r in w["reasons"] for i in r["receipts"]][:15]}
    if tool == "injuries":
        inj = [e for e in ev if e["type"] == "injury_stoppage"]
        if not inj: return {"text": "No injury stoppage was recorded in this match.", "receipts": []}
        return {"text": "Injury stoppages: " + "; ".join(f'{e["player"]} ({e["team"]}) in minute {e["minute"]+1}, play stopped for {e["duration_s"]} seconds, ' + ("substituted off" if e["outcome"] == "substituted" else "carried on") for e in inj) + ".",
                "receipts": [e["id"] for e in inj]}
    if tool == "substitutions":
        sb = [e for e in ev if e["type"] == "substitution"]
        if not sb: return {"text": "No substitutions were made.", "receipts": []}
        return {"text": "Substitutions: " + "; ".join(f'{e["team"]} minute {e["minute"]+1}, {e["player"]} replaced {e.get("replaces")} ({e.get("reason", "tactical")})' for e in sb) + ".", "receipts": [e["id"] for e in sb]}
    if tool == "formation":
        sd = _side_of(me, args.get("team"))
        if not sd: return None
        L = me["lineups"][sd]["players"]; D = [p["pos"] for p in L if p["pos"] in ("RB", "CB", "LB", "RWB", "LWB")]
        Mi = [p["pos"] for p in L if p["pos"] in ("DM", "CM", "AM", "RM", "LM")]; F = [p["pos"] for p in L if p["pos"] in ("LW", "RW", "ST", "CF")]
        if len(D) + len(Mi) + len(F) != 10: return None
        club = me["home"] if sd == "home" else me["away"]
        return {"text": f'{club} started in a {len(D)}-{len(Mi)}-{len(F)} shape: {len(D)} defenders ({", ".join(D)}), {len(Mi)} midfielders ({", ".join(Mi)}) and {len(F)} forwards ({", ".join(F)}), plus the goalkeeper. This is read from the starting positions in the lineup; changes of shape during play are not recorded.', "receipts": []}
    if tool == "lineup_info":
        sd = _side_of(me, args.get("team"))
        if not sd: return None
        L = me["lineups"][sd]["players"]
        return {"text": f'{side_name(sd)} started: ' + ", ".join(f'{p["name"]} ({p["pos"]})' for p in L) + ".", "receipts": []}
    return None

CANNOT = "The match data cannot tell us this: "

class MockPlanner:
    """Keyword planner used offline so the pipeline can be tested without Azure."""
    def plan(self, m, q):
        ql = q.lower(); me = m["meta"]
        if "rated" in ql or "rating" in ql or "best player" in ql: return [{"tool": "top_rated", "args": {"n": 3}}]
        if any(w in ql for w in ["why", "deserve", "unlucky", "lucky"]): return [{"tool": "why_result", "args": {}}]
        if "injur" in ql and "how long" not in ql: return [{"tool": "injuries", "args": {}}]
        if "substitut" in ql and "right" not in ql: return [{"tool": "substitutions", "args": {}}]
        if "formation" in ql or "shape" in ql: return [{"tool": "formation", "args": {"team": me["home"] if "home" in ql else me["away"]}}]
        if any(w in ql for w in ["how long", "tired", "fatigue", "tactic", "manager", "coach", "instruct", "speed", "km", "feel", "best player in the league", "last season", "transfer"]):
            return {"unanswerable": "this is not recorded in the event log"}
        if ("goal" in ql or "scor" in ql) and ("who" in ql or "when" in ql): return [{"tool": "score_timeline", "args": {}}]
        for st in STATS:
            if st in ql or st.rstrip("s") in ql:
                if "most" in ql or "who" in ql: return [{"tool": "top_players", "args": {"stat": st, "n": 3}}]
                side = "home" if me["home"].lower() in ql else "away" if me["away"].lower() in ql else None
                if side: return [{"tool": "team_stat", "args": {"side": side, "stat": st}}]
        for _, name, _, _ in _players(m):
            if name.lower() in ql or name.split()[-1].lower() in ql: return [{"tool": "rating", "args": {"player": name}}]
        return {"unanswerable": "no tool matches this question"}

def facts_for(m, calls):
    facts = []
    for c in calls[:4]:
        r = run_tool(m, c.get("tool"), c.get("args"))
        if r: facts.append({"id": len(facts) + 1, "text": r["text"], "receipts": r["receipts"],
                            "claim": {"kind": "tool", "text": r["text"], "params": {"tool": c.get("tool"), "args": c.get("args") or {}, "text": r["text"]}}})
    return facts


def answer(m, question, llm, audience="fan", lang="English"):
    """Plan -> run deterministic tools -> write -> re-check (rules + judge) -> answer with receipts, or 'cannot tell'."""
    from agents import checker
    trace = []
    plan = llm.plan(m, question)
    if isinstance(plan, dict):
        trace.append({"agent": "Planner", "event": "unanswerable: " + plan["unanswerable"]})
        return {"question": question, "status": "cannot_tell", "answer": CANNOT + plan["unanswerable"].strip().rstrip(".") + ".", "sentences": [], "trace": trace}
    facts = facts_for(m, plan); fb = {f["id"]: f for f in facts}
    trace.append({"agent": "Planner", "event": "calls: " + ", ".join(c.get("tool", "?") for c in plan)})
    if not facts:
        trace.append({"agent": "Tools", "event": "no tool could answer"})
        return {"question": question, "status": "cannot_tell", "answer": CANNOT + "none of the available lookups can answer it from this event log.", "sentences": [], "trace": trace}
    raw = llm.answer_write(question, facts, audience, lang)
    only_inj = all(c.get("tool") == "injuries" for c in plan)   # a "none recorded" result is itself the answer
    if raw.get("answers_question") is False and not only_inj:
        trace.append({"agent": "Storyteller", "event": "the lookups do not answer what was asked"})
        return {"question": question, "status": "cannot_tell", "answer": CANNOT + "none of the available lookups covers what was asked.", "sentences": [], "trace": trace}
    w = raw["sentences"]
    items = [{"i": i, "sentence": s["text"], "cited_facts": [fb[x]["text"] for x in s["fact_ids"] if x in fb]} for i, s in enumerate(w)]
    judged = llm.judge(items) if items else []
    out = []
    for i, s in enumerate(w):
        ok, why, _ = checker(m, s, fb)
        if ok and re.search(r"\bthe (provided )?facts\b.*\b(do not|don't|does not|doesn't|not state|only)\b", s["text"].lower()): ok, why = False, "filler about the facts"
        if ok and judged[i]:
            rec = sorted({r for x in s["fact_ids"] for r in fb[x]["receipts"]})
            out.append({"text": s["text"], "fact_ids": s["fact_ids"], "receipts": rec})
        else:
            reason = why if not ok else "not fully supported"
            trace.append({"agent": "Judge" if ok else "FactChecker", "event": "blocked a sentence: " + reason})
            s2 = llm.fix(s, fb, reason)
            if s2:
                ok2, _, _ = checker(m, s2, fb)
                if ok2 and llm.judge([{"i": 0, "sentence": s2["text"], "cited_facts": [fb[x]["text"] for x in s2["fact_ids"] if x in fb]}])[0]:
                    out.append({"text": s2["text"], "fact_ids": s2["fact_ids"], "receipts": sorted({r for x in s2["fact_ids"] for r in fb[x]["receipts"]})})
                    trace.append({"agent": "Editor", "event": "rewrote the sentence; re-check passed"})
    if not out:   # nothing survived: fall back to the tool facts themselves, which are true by construction
        out = [{"text": f["text"], "fact_ids": [f["id"]], "receipts": f["receipts"]} for f in facts]
        trace.append({"agent": "Editor", "event": "used the verified tool output directly"})
    return {"question": question, "status": "answered", "answer": " ".join(s["text"] for s in out), "sentences": out, "trace": trace}

QUESTIONS = [  # (question, should_be_answerable)
    ("Who scored and when?", True), ("Who had the most tackles?", True), ("Why did the home team not win?", True),
    ("How many shots did the away team have?", True), ("Who made the most interceptions?", True), ("How many fouls did the home team commit?", True),
    ("Which player was rated highest and why?", True), ("How many shots did the home team have between minute 60 and 90?", True),
    ("Was the manager right to make that substitution?", False), ("Was anyone injured or tired in the second half?", False),
    ("What formation did the away team play?", True), ("How fast did the fastest player run?", False),
    ("Is this team better than Bayern Munich?", False), ("Who will win the next match?", False)]

QUESTIONS_SITE = [  # asked on every match on the website
    ("Who scored and when?", True), ("Why did the result go the way it did?", True), ("Which player was rated highest and why?", True),
    ("How many shots did the home team have in the second half?", True), ("Who had the most tackles?", True), ("How many fouls did the away team commit?", True),
    ("Who made the most interceptions?", True),
    ("Was anyone injured?", True),
    ("What formation did the away team play?", True), ("How long will the injured player be out for?", False), ("Was the referee right to book that player?", False)]
