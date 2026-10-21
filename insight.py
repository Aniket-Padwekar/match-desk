"""Ratings explainer and 'why the result defied the chances' explainer, both with receipts."""
from collections import defaultdict
from engine import ev_of, summarize, verdict, goals_list

# Published rating formula (every term is listed so a user can audit a rating)
W = {"goal": 0.9, "shot_xg": 0.6, "progressive_pass": 0.02, "pass_ok": 0.002, "pass_lost": -0.04,
     "dribble": 0.03, "tackle": 0.10, "interception": 0.08, "duel": 0.05, "foul": -0.10,
     "yellow_card": -0.30, "save": 0.25, "block": 0.08}

def ratings(m):
    ev = m["events"]; R = defaultdict(lambda: {"base": 6.0, "parts": defaultdict(lambda: [0.0, []]), "touches": 0})
    names = {}
    for side in ("home", "away"):
        for p in m["meta"]["lineups"][side]["players"] + m["meta"]["lineups"][side]["bench"]:
            names[p["id"]] = (p["name"], side, p["pos"])
    def add(e, key, delta):
        pid = e["player_id"]
        if pid is None: return
        R[pid]["parts"][key][0] += delta; R[pid]["parts"][key][1].append(e["id"])
    for e in ev:
        t = e["type"]
        if t == "goal": add(e, "goals", W["goal"])
        elif t == "shot": add(e, "shot quality (xG)", W["shot_xg"] * e["xg"])
        elif t == "pass":
            if e["outcome"] == "complete":
                add(e, "passing", W["pass_ok"] + (W["progressive_pass"] if e.get("progressive") else 0))
            else: add(e, "lost passes", W["pass_lost"])
            if e["player_id"]: R[e["player_id"]]["touches"] += 1
        elif t == "dribble": add(e, "dribbles", W["dribble"]); R[e["player_id"]]["touches"] += 1
        elif t == "tackle": add(e, "tackles", W["tackle"])
        elif t == "interception": add(e, "interceptions", W["interception"])
        elif t == "duel": add(e, "duels won", W["duel"])
        elif t == "foul": add(e, "fouls", W["foul"])
        elif t == "yellow_card": add(e, "yellow card", W["yellow_card"])
        elif t == "save": add(e, "saves", W["save"])
        elif t == "block": add(e, "blocks", W["block"])
    out = {}
    for pid, r in R.items():
        if pid not in names: continue
        total = r["base"] + sum(v[0] for v in r["parts"].values())
        drivers = sorted(((k, round(v[0], 2), v[1]) for k, v in r["parts"].items()), key=lambda x: -abs(x[1]))
        out[pid] = {"player": names[pid][0], "side": names[pid][1], "pos": names[pid][2],
                    "rating": round(max(3.0, min(10.0, total)), 1), "touches": r["touches"], "drivers": drivers}
    return out

def explain_rating(m, pid):
    r = ratings(m)[pid]
    top = [d for d in r["drivers"] if abs(d[1]) >= 0.1][:3]
    bits = ", ".join(f'{k.split(" (")[0]} ({d:+.1f})' for k, d, _ in top) or "many small contributions"
    return {"player": r["player"], "rating": r["rating"], "touches": r["touches"],
            "text": f'{r["player"]} rated {r["rating"]}: base 6.0 plus {bits}.',
            "receipts": [i for _, _, ids in top for i in ids][:12]}

def why_result(m):
    """Explains a result that differs from the chances. Returns None when result matched."""
    v = verdict(m)
    if v["label"] in ("matched", "even"): return None
    ev, meta = m["events"], m["meta"]; S = summarize(m)
    lead = "home" if v["xg_diff"] > 0 else "away"; other = "away" if lead == "home" else "home"
    L, O = meta[lead], meta[other]
    reasons = []
    # finishing
    lg, lx = S[lead]["goals"], S[lead]["xg"]
    if lx - lg >= 0.8:
        misses = [e for e in ev_of(ev, type="shot", side=lead) if e["outcome"] != "goal"]
        big = sorted(misses, key=lambda e: -e["xg"])[:3]
        reasons.append({"kind": "finishing", "text": f'{L} scored {lg} from {lx} expected goals; their three best misses were worth {sum(e["xg"] for e in big):.2f}.',
                        "receipts": [e["id"] for e in big]})
    # keeper
    saves = ev_of(ev, type="save", side=other)
    on_target_faced = sum(1 for e in ev_of(ev, type="shot", side=lead) if e["outcome"] in ("saved", "goal"))
    if len(saves) >= 4:
        reasons.append({"kind": "keeper", "text": f'{O} goalkeeper made {len(saves)} saves.', "receipts": [e["id"] for e in saves][:6]})
    # shot quality
    shots = ev_of(ev, type="shot", side=lead)
    if shots:
        avg = S[lead]["xg"] / len(shots)
        if len(shots) >= 14 and avg < 0.08:
            low = sum(1 for e in shots if e["xg"] < 0.05)
            reasons.append({"kind": "shot_quality", "text": f'{L} took {len(shots)} shots, but {low} were low-value (under 0.05 expected goals each), averaging {avg:.2f}.',
                            "receipts": [e["id"] for e in shots if e["xg"] < 0.05][:8]})
    # blocked
    blocks = [e for e in shots if e["outcome"] == "blocked"]
    if len(blocks) >= 4:
        reasons.append({"kind": "blocked", "text": f'{len(blocks)} of the shots by {L} were blocked before reaching the goal.', "receipts": [e["id"] for e in blocks][:6]})
    # other side's clinical efficiency
    og, ox = S[other]["goals"], S[other]["xg"]
    if og - ox >= 0.8:
        reasons.append({"kind": "opponent_clinical", "text": f'{O} scored {og} from only {ox} expected goals.', "receipts": [g["id"] for g in goals_list(ev) if g["side"] == other]})
    if not reasons:
        reasons.append({"kind": "variance", "text": "No single cause stands out; the gap is within normal match-to-match variation.", "receipts": []})
    res = f'{meta["home"]} {S["home"]["goals"]}-{S["away"]["goals"]} {meta["away"]}'
    head = (f'{L} created more ({S[lead]["xg"]} vs {S[other]["xg"]} expected goals) but {"did not win" if S[lead]["goals"] <= S[other]["goals"] else "won"}: {res}.')
    return {"headline": head, "label": v["label"], "reasons": reasons}

if __name__ == "__main__":
    from simulate import simulate
    found = 0
    for s in range(1, 400):
        m = simulate(s); w = why_result(m)
        if w and w["label"] == "against_run_of_play" and found < 2:
            found += 1; print("SEED", s); print(w["headline"])
            for r in w["reasons"]: print(" -", r["text"], r["receipts"][:4])
    m = simulate(3); rt = ratings(m)
    top = sorted(rt, key=lambda k: -rt[k]["rating"])[:2]
    for pid in top: print(explain_rating(m, pid)["text"])
    lows = sorted(((r["rating"], r["touches"], r["player"]) for r in rt.values() if r["touches"] < 25 and r["rating"] >= 7.0))
    print("high rating, few touches:", lows[:3])
