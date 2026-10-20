"""A small fictional league: 16 clubs, 8 matches per matchweek, 3 matchweeks (24 matches). All made up."""
from simulate import CLUBS, simulate

LEAGUE = [c for c in CLUBS if c not in ("Hollowdene", "Saltmarsh United", "Larkhill Athletic", "Wexcombe City")]
assert len(LEAGUE) == 16
WEEKS = 3
# kick-off slots for the 8 matches of a matchweek (day offset from the Saturday, time)
SLOTS = [(0, "12:30"), (0, "15:00"), (0, "15:00"), (0, "15:00"), (0, "17:30"), (1, "14:00"), (1, "14:00"), (1, "16:30")]
FIRST_SATURDAY = (2026, 10, 24)

def rounds():
    """Circle method: every club plays once per round."""
    n = len(LEAGUE); teams = LEAGUE[:]; out = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = teams[i], teams[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))   # alternate home and away
        out.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return out

def seed_for(week, i): return 100 * week + i + 1

def fixtures():
    """[{week, index, seed, home, away, day, time}]"""
    import datetime
    sat = datetime.date(*FIRST_SATURDAY); res = []
    for w, pairs in enumerate(rounds()[:WEEKS], start=1):
        for i, (h, a) in enumerate(pairs):
            d, t = SLOTS[i]; date = sat + datetime.timedelta(days=7 * (w - 1) + d)
            res.append({"week": w, "index": i, "seed": seed_for(w, i), "home": h, "away": a, "date": date.isoformat(), "time": t})
    return res

def match_for(fx):
    return simulate(fx["seed"], home=fx["home"], away=fx["away"])

def table(results_by_week, upto):
    """results: {week: [(home, away, hg, ag)]} -> sorted table after matchweek `upto`."""
    t = {c: dict(club=c, p=0, w=0, d=0, l=0, gf=0, ga=0, pts=0) for c in LEAGUE}
    for w in range(1, upto + 1):
        for h, a, hg, ag in results_by_week.get(w, []):
            for c, gf, ga in ((h, hg, ag), (a, ag, hg)):
                r = t[c]; r["p"] += 1; r["gf"] += gf; r["ga"] += ga
                if gf > ga: r["w"] += 1; r["pts"] += 3
                elif gf == ga: r["d"] += 1; r["pts"] += 1
                else: r["l"] += 1
    rows = sorted(t.values(), key=lambda r: (-r["pts"], -(r["gf"] - r["ga"]), -r["gf"], r["club"]))
    for i, r in enumerate(rows, 1): r["pos"] = i; r["gd"] = r["gf"] - r["ga"]
    return rows
