"""Builds docs/data/matches.json (and placeholder recaps/ask files if the real ones are missing).
Everything in matches.json is computed by code from the synthetic event log. No model involved."""
import json, os, re, datetime
from simulate import simulate
from engine import key_moments, verdict, team_stat, possession, summarize
from insight import ratings, why_result
from agents import analyst, MockLLM, pipeline
from ask import answer, QUESTIONS_SITE

SEEDS = [1, 4, 5, 12, 18, 20, 23, 32]
OUT = "docs/data"
COLS = ["id", "minute", "second", "type", "side", "player", "x", "y", "end_x", "end_y", "xg", "outcome"]

def fact_events(m, f):
    c = f["claim"]; k, p, ev = c["kind"], c["params"], m["events"]
    if k in ("goal", "score_after"): return [p.get("event_id")] if p.get("event_id") else [e["id"] for e in ev if e["type"] == "goal" and e["minute"] == p.get("minute")][:1]
    if k == "big_chance": return [p.get("event_id")] if p.get("event_id") else []
    if k == "team_stat":
        t = {"shots": "shot", "goals": "goal", "saves": "save", "tackles": "tackle", "corners": "corner"}.get(p.get("stat"))
        return [e["id"] for e in ev if t and e["type"] == t and e["side"] == p.get("side")]
    if k == "final_score": return [e["id"] for e in ev if e["type"] == "goal"]
    if k == "why": return [i for r in (why_result(m) or {}).get("reasons", []) if r["text"] == p["reason"] for i in r["receipts"]]
    if k == "spell": return [e["id"] for e in ev if e["type"] == "shot" and e["side"] == p["side"] and p["lo"] <= e["minute"] < p["hi"]]
    if k == "rating":
        return [e["id"] for e in ev if e.get("player_id") == p["pid"] and e["type"] in ("goal", "shot", "save", "tackle", "interception")][:12]
    return []

def timeline(m):
    me = m["meta"]; out = []
    for k in key_moments(m):
        mi = k["minute"] + 1
        if k["kind"] == "goal": t, at = f'GOAL. {k["player"]} scores for {k["team"]}. It is {k["score"].replace("-", "–")}. Chance quality {k["xg"]}.', mi
        elif k["kind"] == "big_chance_missed": t, at = f'Big chance missed: {k["player"]} ({k["team"]}), worth {k["xg"]} goals, {k["outcome"].replace("_", " ")}.', mi
        elif k["kind"] == "card": t, at = f'Yellow card for {k["player"]} ({k["team"]}).', mi
        else: t, at = f'{k["team"]} had {int(k["possession"])}% of the touches between minute {k["minute"]+1} and {k["to"]} and led the chances by {k["xg_diff"]}.', k["to"]
        out.append({"minute": at, "kind": k["kind"], "side": k["side"], "text": t, "events": k["event_ids"]})
    for e in m["events"]:
        if e["type"] == "substitution": out.append({"minute": e["minute"] + 1, "kind": "sub", "side": e["side"], "text": f'Substitution for {e["team"]}: {e["player"]} replaces {e.get("replaces")}.', "events": [e["id"]]})
    out.sort(key=lambda x: x["minute"]); return out

def build():
    matches = []
    for s in SEEDS:
        m = simulate(s); me = m["meta"]; ev = m["events"]; case = analyst(m)
        v = verdict(m); label = v["label"] if isinstance(v, dict) else v
        stats = {sd: {"shots": team_stat(ev, sd, "shots"), "xg": team_stat(ev, sd, "xg"), "goals": team_stat(ev, sd, "goals"),
                      "saves": team_stat(ev, sd, "saves"), "poss": possession(ev, sd), "fouls": sum(1 for e in ev if e["type"] == "foul" and e["side"] == sd),
                      "cards": team_stat(ev, sd, "cards")} for sd in ("home", "away")}
        rt = ratings(m); top = sorted(rt.items(), key=lambda kv: -kv[1]["rating"])[:3]
        matches.append({"id": me["match_id"], "seed": s, "home": me["home"], "away": me["away"],
                        "score": [me["final_score"]["home"], me["final_score"]["away"]], "label": label,
                        "cols": COLS, "events": [[e.get(c) for c in COLS] for e in ev if e["type"] not in ("possession_change", "kickoff")],
                        "timeline": timeline(m), "stats": stats,
                        "facts": [{"id": f["id"], "text": f["text"], "events": [i for i in fact_events(m, f) if i]} for f in case["facts"]],
                        "top_rated": [{"player": r["player"], "rating": r["rating"]} for _, r in top]})
    json.dump({"built": datetime.date.today().isoformat(), "matches": matches}, open(f"{OUT}/matches.json", "w"), separators=(",", ":"))
    return matches

def placeholders(matches):
    """Offline stand-in output so the site can be previewed. The real files come from colab_build_site.py."""
    if not os.path.exists(f"{OUT}/recaps.json"):
        rec = {}
        for mm in matches:
            m = simulate(mm["seed"]); rec[mm["id"]] = {}
            for aud, lang in (("fan", "English"), ("analyst", "English"), ("coach", "German")):
                out = pipeline(m, MockLLM(0, 0), audience=aud, lang=lang)
                for s in out["sentences"]: s.pop("_mutated", None); s["text"] = s["text"].replace("..", ".")
                rec[mm["id"]][f"{aud}:{lang}"] = {"headline": out["headline"], "sentences": out["sentences"], "trace": out["trace"], "stats": out["stats"]}
        json.dump({"source": "placeholder", "model": "offline stand-in (no AI)", "recaps": rec}, open(f"{OUT}/recaps.json", "w"), separators=(",", ":"))
    if not os.path.exists(f"{OUT}/ask.json"):
        ask = {}
        for mm in matches:
            m = simulate(mm["seed"]); ask[mm["id"]] = []
            for q, can in QUESTIONS_SITE:
                r = answer(m, q, MockLLM(0, 0)); ask[mm["id"]].append({k: r[k] for k in ("question", "status", "answer", "sentences", "trace")})
        json.dump({"source": "placeholder", "model": "offline stand-in (no AI)", "ask": ask}, open(f"{OUT}/ask.json", "w"), separators=(",", ":"))
    if not os.path.exists(f"{OUT}/scorecard.json"):
        json.dump({"source": "measured", "model": "gpt-5-mini", "matches": 6, "planted_errors": 392, "caught": 387, "true_sentences": 120, "wrongly_blocked": 0,
                   "by_kind": {"wrong number": [114, 114], "swapped team": [44, 44], "invented cause": [114, 114], "flipped comparison": [6, 6], "wrong citation": [109, 114]},
                   "recap_first_pass": {"drafted": 18, "blocked": 1}}, open(f"{OUT}/scorecard.json", "w"), indent=1)

if __name__ == "__main__":
    ms = build(); placeholders(ms)
    for f in os.listdir(OUT): print(f, os.path.getsize(f"{OUT}/{f}") // 1024, "KB")
