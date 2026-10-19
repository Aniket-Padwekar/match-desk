"""Match Desk engine: stats, key moments, result-vs-chances verdict, claims with receipts,
an independent verifier, and a planted-error test harness. No LLM needed for this layer."""
import json, random, statistics as st
from collections import defaultdict

def load(path): return json.load(open(path))

# ---------- basic queries (the verifier uses ONLY these, straight from the event log) ----------
def ev_of(events, **kw):
    return [e for e in events if all(e.get(k) == v for k, v in kw.items())]

def team_stat(events, side, stat):
    if stat == "shots":   return len(ev_of(events, type="shot", side=side))
    if stat == "xg":      return round(sum(e["xg"] for e in ev_of(events, type="shot", side=side)), 2)
    if stat == "goals":   return len(ev_of(events, type="goal", side=side))
    if stat == "passes":  return len(ev_of(events, type="pass", side=side))
    if stat == "cards":   return len(ev_of(events, type="yellow_card", side=side))
    if stat == "corners": return len(ev_of(events, type="corner", side=side))
    if stat == "tackles": return len(ev_of(events, type="tackle", side=side))
    if stat == "saves":   return len(ev_of(events, type="save", side=side))
    raise KeyError(stat)

def touches(events, side, lo=0, hi=200):
    return sum(1 for e in events if e["side"] == side and e["type"] in ("pass", "dribble") and lo <= e["minute"] < hi)

def possession(events, side, lo=0, hi=200):
    a, b = touches(events, side, lo, hi), touches(events, "away" if side == "home" else "home", lo, hi)
    return round(100 * a / (a + b), 0) if a + b else 50

def goals_list(events): return ev_of(events, type="goal")

# ---------- stats + key moments ----------
def summarize(m):
    ev, meta = m["events"], m["meta"]
    S = {}
    for side in ("home", "away"):
        S[side] = {k: team_stat(ev, side, k) for k in ("shots", "xg", "goals", "passes", "cards", "corners", "tackles")}
        S[side]["possession"] = possession(ev, side)
        fin = [e for e in ev if e["side"] == side and e["type"] == "pass" and e.get("end_x", 0) > 66.7]
        S[side]["final_third_passes"] = len(fin)
    return S

def key_moments(m):
    ev = m["events"]; out = []
    for g in goals_list(ev):
        out.append({"kind": "goal", "minute": g["minute"], "event_ids": [g["id"]], "team": g["team"], "side": g["side"],
                    "player": g["player"], "xg": g["xg"], "score": f'{g["score_home"]}-{g["score_away"]}', "importance": 10})
    for s in ev_of(ev, type="shot"):
        if s["outcome"] != "goal" and s["xg"] >= 0.30:
            out.append({"kind": "big_chance_missed", "minute": s["minute"], "event_ids": [s["id"]], "team": s["team"],
                        "side": s["side"], "player": s["player"], "xg": s["xg"], "outcome": s["outcome"], "importance": 6 + s["xg"]})
    for c in ev_of(ev, type="yellow_card"):
        out.append({"kind": "card", "minute": c["minute"], "event_ids": [c["id"]], "team": c["team"], "side": c["side"],
                    "player": c["player"], "importance": 3})
    # momentum spells: 15-minute windows with >=62% touches and an xG lead
    for lo in range(0, 90, 15):
        for side in ("home", "away"):
            p = possession(ev, side, lo, lo + 15)
            xs = lambda sd: sum(e["xg"] for e in ev if e["type"] == "shot" and e["side"] == sd and lo <= e["minute"] < lo + 15)
            other = "away" if side == "home" else "home"
            if p >= 60 and xs(side) - xs(other) >= 0.4:
                ids = [e["id"] for e in ev if e["type"] == "shot" and e["side"] == side and lo <= e["minute"] < lo + 15]
                out.append({"kind": "spell", "minute": lo, "to": lo + 15, "event_ids": ids, "team": m["meta"][side],
                            "side": side, "possession": p, "xg_diff": round(xs(side) - xs(other), 2), "importance": 5})
    return sorted(out, key=lambda k: (-k["importance"], k["minute"]))[:12]

def verdict(m):
    S = summarize(m); h, a = S["home"], S["away"]
    xd = round(h["xg"] - a["xg"], 2); gd = h["goals"] - a["goals"]
    if abs(xd) < 0.5 and abs(gd) <= 1: label = "even"
    elif (xd > 0 and gd > 0) or (xd < 0 and gd < 0): label = "matched"
    elif gd == 0: label = "draw_vs_edge"
    else: label = "against_run_of_play"
    return {"xg_diff": xd, "goal_diff": gd, "label": label}

# ---------- claims (what a writer asserts) ----------
def make_claims(m):
    ev, meta = m["events"], m["meta"]; S = summarize(m); claims = []
    def add(kind, text, **p): claims.append({"id": len(claims) + 1, "kind": kind, "text": text, "params": p})
    h, a = meta["home"], meta["away"]
    add("final_score", f'{h} {S["home"]["goals"]}-{S["away"]["goals"]} {a}', home=S["home"]["goals"], away=S["away"]["goals"])
    for g in goals_list(ev):
        add("goal", f'{g["player"]} scored for {g["team"]} in minute {g["minute"]+1}', player=g["player"], side=g["side"], minute=g["minute"])
    for side in ("home", "away"):
        add("team_stat", f'{meta[side]} had {S[side]["shots"]} shots', side=side, stat="shots", value=S[side]["shots"])
        add("team_stat", f'{meta[side]} created {S[side]["xg"]} expected goals', side=side, stat="xg", value=S[side]["xg"])
        add("team_stat", f'{meta[side]} scored {S[side]["goals"]}', side=side, stat="goals", value=S[side]["goals"])
        add("team_stat", f'{meta[side]} goalkeeper made {team_stat(ev, side, "saves")} saves', side=side, stat="saves", value=team_stat(ev, side, "saves"))
    add("possession", f'{h} had {S["home"]["possession"]:.0f}% of the touches', side="home", value=S["home"]["possession"])
    for k in key_moments(m):
        if k["kind"] == "big_chance_missed":
            add("big_chance", f'{k["player"]} ({k["team"]}) had a big chance in minute {k["minute"]+1}', player=k["player"], side=k["side"], minute=k["minute"]); break
    return claims

# ---------- independent verifier ----------
def verify(claim, m, tol_xg=0.05):
    ev, p, k = m["events"], claim["params"], claim["kind"]
    if k == "final_score":
        ok = team_stat(ev, "home", "goals") == p["home"] and team_stat(ev, "away", "goals") == p["away"]
        return ok, "goal events" if ok else "score differs from goal events"
    if k == "goal":
        hits = [g for g in goals_list(ev) if g["player"] == p["player"] and g["side"] == p["side"] and g["minute"] == p["minute"]]
        return bool(hits), (f'event #{hits[0]["id"]}' if hits else "no matching goal event")
    if k == "team_stat":
        v = team_stat(ev, p["side"], p["stat"])
        ok = abs(v - p["value"]) <= (tol_xg if p["stat"] == "xg" else 0)
        return ok, f'log says {v}'
    if k == "possession":
        v = possession(ev, p["side"]); return abs(v - p["value"]) <= 1, f'log says {v}%'
    if k == "big_chance":
        hits = [s for s in ev_of(ev, type="shot") if s["player"] == p["player"] and s["side"] == p["side"] and s["minute"] == p["minute"] and s["xg"] >= 0.30]
        return bool(hits), (f'event #{hits[0]["id"]}' if hits else "no big-chance shot found")
    raise KeyError(k)

# ---------- planted errors ----------
def plant_error(claim, m, rng):
    c = json.loads(json.dumps(claim)); p = c["params"]; k = c["kind"]; meta = m["meta"]
    if k == "final_score": p["home"] += rng.choice([1, -1]) if p["home"] > 0 else 1; c["text"] = "[wrong score]"
    elif k == "goal": p["minute"] += rng.choice([-9, -4, 3, 6, 11])
    elif k == "team_stat":
        if p["stat"] == "xg": p["value"] = round(p["value"] + rng.choice([-0.6, 0.5, 0.9]), 2)
        else: p["value"] += rng.choice([-3, -2, 2, 4])
    elif k == "possession": p["value"] = p["value"] + rng.choice([-12, -8, 9, 14])
    elif k == "big_chance": p["minute"] += rng.choice([-7, 5, 12])
    return c

def scorecard(n_matches=30, errors_per_match=3, seed=7):
    from simulate import simulate
    rng = random.Random(seed); caught = missed = false_block = true_pass = 0
    by_kind = defaultdict(lambda: [0, 0])
    for s in range(1, n_matches + 1):
        m = simulate(s); cl = make_claims(m)
        idx = set(rng.sample(range(len(cl)), min(errors_per_match, len(cl))))
        for i, c in enumerate(cl):
            c2 = plant_error(c, m, rng) if i in idx else c
            ok, _ = verify(c2, m)
            if i in idx:
                by_kind[c["kind"]][1] += 1
                if not ok: caught += 1; by_kind[c["kind"]][0] += 1
                else: missed += 1
            else:
                if ok: true_pass += 1
                else: false_block += 1
    total_err = caught + missed; total_ok = true_pass + false_block
    return {"matches": n_matches, "planted_errors": total_err, "caught": caught,
            "catch_rate": round(100 * caught / total_err, 1), "true_claims": total_ok,
            "wrongly_blocked": false_block, "false_block_rate": round(100 * false_block / total_ok, 1),
            "by_kind": {k: f"{v[0]}/{v[1]}" for k, v in by_kind.items()}}

if __name__ == "__main__":
    from simulate import simulate
    m = simulate(3)
    print(json.dumps(summarize(m), indent=1)); print(verdict(m))
    for k in key_moments(m)[:5]: print(k)
    for c in make_claims(m)[:6]: print(c["text"], verify(c, m))
    print(json.dumps(scorecard(), indent=1))
