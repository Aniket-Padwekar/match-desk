# Colab cell: builds ALL the real website data (recaps, answers, scorecard) with your Azure model. Takes about 20-25 minutes.
# Paste into one Colab cell and press play. It asks for 3 values (the key stays hidden).
!pip -q install openai
!rm -rf match-desk && git clone -q https://github.com/Aniket-Padwekar/match-desk.git
import sys, re, json, time
sys.path.insert(0, "match-desk")
for _m in ["agents","engine","insight","simulate","ask"]: sys.modules.pop(_m, None)   # forget old copies from earlier runs
print("GitHub agents.py has the Judge:", "def judge" in open("match-desk/agents.py").read())
from getpass import getpass
from simulate import simulate
from agents import AzureLLM
from ask import answer, QUESTIONS_SITE
from agents import pipeline, real_scorecard
import zipfile
from insight import why_result
if not hasattr(AzureLLM, 'plan'):
    raise SystemExit('STOP: GitHub still has the OLD agents.py (no Judge agent). Upload the new agents.py to the repo first, then run this cell again.')

endpoint = input("Endpoint: ").strip()
m_ = re.match(r"(https://[^/]+)", endpoint); endpoint = (m_.group(1) + "/") if m_ else endpoint
deployment = input("Deployment name (gpt-5-mini): ").strip() or "gpt-5-mini"
key = getpass("API key (hidden): ").strip()
llm = AzureLLM(endpoint, key, deployment)


SEEDS = [1, 4, 5, 12, 18, 20, 23, 32]
RECAPS = [("fan", "English"), ("analyst", "English"), ("coach", "German")]
recaps, ask, tot = {}, {}, dict(drafted=0, blocked=0)
for n, seed in enumerate(SEEDS, 1):
    m = simulate(seed); mid = m["meta"]["match_id"]; recaps[mid] = {}; ask[mid] = []
    print(f"\n[{n}/{len(SEEDS)}] {m['meta']['home']} {m['meta']['final_score']['home']}-{m['meta']['final_score']['away']} {m['meta']['away']}")
    for aud, lang in RECAPS:
        try: out = pipeline(m, llm, audience=aud, lang=lang)
        except Exception as e: print("  recap FAILED", aud, str(e)[:150]); continue
        for s in out["sentences"]: s.pop("_mutated", None)
        recaps[mid][f"{aud}:{lang}"] = {k: out[k] for k in ("headline", "sentences", "trace", "stats")}
        tot["drafted"] += out["stats"]["drafted"]; tot["blocked"] += out["stats"]["blocked_first_pass"]
        print(f"  recap {aud}/{lang}: {out['stats']}")
    for q, can in QUESTIONS_SITE:
        try: r = answer(m, q, llm)
        except Exception as e: print("  ask FAILED", q, str(e)[:150]); continue
        ask[mid].append({k: r[k] for k in ("question", "status", "answer", "sentences", "trace")})
    print("  questions done:", len(ask[mid]))
print("\n=== SCORECARD (planted errors) ===")
sc = real_scorecard(llm, n_matches=6, verbose=False)
names = {"wrong_number": "wrong number", "wrong_team": "swapped team", "invented_cause": "invented cause", "flipped_comparison": "flipped comparison", "wrong_citation": "wrong citation"}
score = {"source": "measured", "model": deployment, "matches": 6, "planted_errors": sc["planted_errors"], "caught": sc["caught"],
         "true_sentences": sc["true_sentences"], "wrongly_blocked": sc["wrongly_blocked"],
         "by_kind": {names[k]: v for k, v in sc["by_kind(blocked,total)"].items() if k in names}, "missed_examples": sc["missed_examples"],
         "recap_first_pass": tot}
print(json.dumps(score, indent=1, ensure_ascii=False))
files_ = {"recaps.json": {"source": "azure", "model": deployment, "recaps": recaps}, "ask.json": {"source": "azure", "model": deployment, "ask": ask}, "scorecard.json": score}
with zipfile.ZipFile("site_data.zip", "w") as z:
    for name, obj in files_.items(): z.writestr(name, json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
print("\nDONE. Downloading site_data.zip")
try:
    from google.colab import files; files.download("site_data.zip")
except Exception: pass
