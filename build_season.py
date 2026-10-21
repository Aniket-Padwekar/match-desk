"""Builds the code-computed part of the site (no model involved): docs/data/season.json and docs/data/mw1..3.json.
Text that a model writes (recaps, answers, translations) comes from the Colab run and lives in docs/data/lang/."""
import json, os, datetime
from season import fixtures, match_for, table, LEAGUE, WEEKS
from engine import key_moments, verdict, team_stat, possession
from insight import ratings
from agents import analyst
from build_site import fact_events

OUT = "docs/data"
COLS = ["id", "minute", "second", "type", "side", "player", "x", "y", "end_x", "end_y", "xg", "outcome", "possession"]

def timeline(m):
    """Structured (no English sentences): the page fills in the words from the chosen language's templates."""
    out = []
    for k in key_moments(m):
        base = {"minute": (k["to"] if k["kind"] == "spell" else k["minute"] + 1), "kind": k["kind"], "side": k["side"], "team": k["team"], "events": k["event_ids"]}
        if k["kind"] == "goal": base.update(player=k["player"], score=k["score"].replace("-", "–"), xg=k["xg"])
        elif k["kind"] == "big_chance_missed": base.update(player=k["player"], xg=k["xg"], outcome=k["outcome"])
        elif k["kind"] == "card": base.update(player=k["player"])
        else: base.update(frm=k["minute"] + 1, to=k["to"], poss=int(k["possession"]), diff=k["xg_diff"])
        out.append(base)
    for e in m["events"]:
        if e["type"] == "injury_stoppage":
            out.append({"minute": e["minute"] + 1, "kind": "injury", "side": e["side"], "team": e["team"], "player": e["player"], "secs": e["duration_s"], "out": e["outcome"], "events": [e["id"]]})
        if e["type"] == "substitution":
            out.append({"minute": e["minute"] + 1, "kind": "sub", "side": e["side"], "team": e["team"], "player": e["player"], "replaced": e.get("replaces"), "reason": e.get("reason", "tactical"), "events": [e["id"]]})
    out.sort(key=lambda x: x["minute"]); return out

def build_match(fx):
    m = match_for(fx); me = m["meta"]; ev = m["events"]; case = analyst(m)
    stats = {sd: {"shots": team_stat(ev, sd, "shots"), "xg": team_stat(ev, sd, "xg"), "goals": team_stat(ev, sd, "goals"), "saves": team_stat(ev, sd, "saves"),
                  "poss": possession(ev, sd), "fouls": sum(1 for e in ev if e["type"] == "foul" and e["side"] == sd), "cards": team_stat(ev, sd, "cards")} for sd in ("home", "away")}
    rt = ratings(m); top = sorted(rt.items(), key=lambda kv: -kv[1]["rating"])[:3]
    shirts = {p["name"]: p["number"] for sd in ("home", "away") for p in me["lineups"][sd]["players"] + me["lineups"][sd]["bench"]}
    return {"id": me["match_id"], "week": fx["week"], "home": me["home"], "away": me["away"], "date": fx["date"], "time": fx["time"],
            "score": [me["final_score"]["home"], me["final_score"]["away"]], "label": verdict(m)["label"], "shirts": shirts,
            "cols": COLS, "events": [[e.get(c) for c in COLS] for e in ev if e["type"] not in ("possession_change", "kickoff")],
            "timeline": timeline(m), "stats": stats,
            "facts": [{"id": f["id"], "kind": f["claim"]["kind"], "text": f["text"], "events": [i for i in fact_events(m, f) if i]} for f in case["facts"]],
            "top_rated": [{"player": r["player"], "rating": r["rating"]} for _, r in top]}

def build():
    os.makedirs(OUT, exist_ok=True)
    fx = fixtures(); weeks = []; results = {}
    for w in range(1, WEEKS + 1):
        ms = [build_match(f) for f in fx if f["week"] == w]
        results[w] = [(x["home"], x["away"], x["score"][0], x["score"][1]) for x in ms]
        json.dump({"week": w, "matches": ms}, open(f"{OUT}/mw{w}.json", "w"), separators=(",", ":"))
        weeks.append({"n": w, "matches": [{k: x[k] for k in ("id", "home", "away", "score", "date", "time", "label")} for x in ms], "table": table(results, w)})
    json.dump({"built": datetime.date.today().isoformat(), "league": LEAGUE, "weeks": weeks}, open(f"{OUT}/season.json", "w"), separators=(",", ":"))
    return weeks

if __name__ == "__main__":
    wk = build()
    for f in sorted(os.listdir(OUT)): 
        p = f"{OUT}/{f}"
        if os.path.isfile(p): print(f, os.path.getsize(p) // 1024, "KB")
    print([ (m["home"],m["score"],m["away"]) for m in wk[0]["matches"]][:3]); print(wk[2]["table"][:3])
