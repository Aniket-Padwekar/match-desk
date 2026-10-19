# Colab cell: runs Match Desk with your real Azure model on 3 simulated matches.
# Paste into one Colab cell and press play. It asks for 3 values (the key stays hidden).
!pip -q install openai
!rm -rf match-desk && git clone -q https://github.com/Aniket-Padwekar/match-desk.git
import sys, re, json, time
sys.path.insert(0, "match-desk")
for _m in ["agents","engine","insight","simulate","ask"]: sys.modules.pop(_m, None)   # forget old copies from earlier runs
print("GitHub agents.py has the Judge:", "def judge" in open("match-desk/agents.py").read())
from getpass import getpass
from simulate import simulate
from agents import AzureLLM, pipeline, real_scorecard
from insight import why_result
if not hasattr(AzureLLM, 'judge'):
    raise SystemExit('STOP: GitHub still has the OLD agents.py (no Judge agent). Upload the new agents.py to the repo first, then run this cell again.')

endpoint = input("Endpoint: ").strip()
m_ = re.match(r"(https://[^/]+)", endpoint); endpoint = (m_.group(1) + "/") if m_ else endpoint
deployment = input("Deployment name (gpt-5-mini): ").strip() or "gpt-5-mini"
key = getpass("API key (hidden): ").strip()
llm = AzureLLM(endpoint, key, deployment)

jobs = [(24, "fan", "English"), (24, "coach", "German"), (47, "fan", "English")]
results = []
for seed, aud, lang in jobs:
    m = simulate(seed); t0 = time.time()
    try:
        out = pipeline(m, llm, audience=aud, lang=lang)
    except Exception as e:
        print(f"seed {seed} {aud} {lang} FAILED: {str(e)[:300]}"); continue
    out.update({"seed": seed, "match": f'{m["meta"]["home"]} {m["meta"]["final_score"]["home"]}-{m["meta"]["final_score"]["away"]} {m["meta"]["away"]}'})
    for s in out["sentences"]: s.pop("_mutated", None)
    results.append(out)
    print(f'\n=== {out["match"]} | {aud} | {lang} | {round(time.time()-t0)}s | {out["stats"]}')
    print(" HEADLINE:", out.get("headline"))
    for s in out["sentences"]: print(" -", s["text"], s["fact_ids"])
    w = why_result(m)
    if w and aud != "coach": print(" WHY:", w["headline"])
tot_d = sum(r["stats"]["drafted"] for r in results); tot_b = sum(r["stats"]["blocked_first_pass"] for r in results)
print("rules blocked:", sum(r["stats"]["blocked_by_rules"] for r in results), "| judge blocked:", sum(r["stats"]["blocked_by_judge"] for r in results))
print(f"\nDRAFTED {tot_d} sentences, checker blocked {tot_b} on the first pass ({round(100*tot_b/max(tot_d,1),1)}%).")
print("\n=== SCORECARD: planting known errors and checking how many the system catches (about 5-8 minutes) ===")
sc = real_scorecard(llm, n_matches=6)
print(json.dumps(sc, indent=1, ensure_ascii=False))
json.dump({"recaps": results, "scorecard": sc}, open("matchdesk_results.json", "w"), ensure_ascii=False, indent=1)
try:
    from google.colab import files; files.download("matchdesk_results.json")
except Exception: pass
