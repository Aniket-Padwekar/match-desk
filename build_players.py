"""Builds docs/data/players.json: lineups, subs, bench, ratings and cards per match, straight from the simulator. No model, no cost.
Run: python build_players.py"""
import json, season, insight

def side_block(m, sd, R):
    me = m["meta"]; L = me["lineups"][sd]; ev = m["events"]
    byid = {p["name"]: p for p in L["players"] + L["bench"]}
    subs = [e for e in ev if e["type"] == "substitution" and e["side"] == sd]
    off = {e["replaces"]: e for e in subs}; on = {e["player"]: e for e in subs}
    def card_mins(name): return [e["minute"] + 1 for e in ev if e["type"] == "yellow_card" and e.get("player") == name]
    def goal_mins(name): return [e["minute"] + 1 for e in ev if e["type"] == "goal" and e.get("player") == name]
    def row(p):
        r = R.get(p["id"]); o = off.get(p["name"]); i = on.get(p["name"])
        return {"name": p["name"], "pos": p["pos"], "n": p["number"], "r": r["rating"] if r else None,
                "off": o["minute"] + 1 if o else None, "on": i["minute"] + 1 if i else None,
                "for": i["replaces"] if i else None, "why": (o or i or {}).get("reason"),
                "cards": card_mins(p["name"]), "goals": goal_mins(p["name"])}
    starters = [row(p) for p in L["players"]]
    used = set(on)
    return {"starters": starters,
            "subs": sorted([row(byid[x]) for x in used if any(b["name"] == x for b in L["bench"])], key=lambda r: r["on"]),
            "bench": [row(b) for b in L["bench"] if b["name"] not in used]}

def build():
    out = {}
    for fx in season.fixtures():
        m = season.match_for(fx); R = insight.ratings(m)
        best = max(R.values(), key=lambda r: r["rating"])
        out[m["meta"]["match_id"]] = {"home": side_block(m, "home", R), "away": side_block(m, "away", R), "best": best["player"]}
    return out

if __name__ == "__main__":
    d = build(); json.dump(d, open("docs/data/players.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(len(d), "matches", len(json.dumps(d)) // 1024, "KB")
