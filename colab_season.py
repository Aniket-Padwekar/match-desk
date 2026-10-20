# Colab cell: builds the model-written part of ONE matchweek (8 matches): recaps, 11 answers per match, and checked translations in 19 languages.
# Run it once per matchweek (1, 2, 3). Keep your laptop awake. It takes about 35-45 minutes per matchweek. Paste into one Colab cell and press play.
!pip -q install openai
!pip -q install --pre agent-framework
!rm -rf match-desk && git clone -q https://github.com/Aniket-Padwekar/match-desk.git
import sys, re, json, os, zipfile, time
sys.path.insert(0, "match-desk")
for _m in ["agents","engine","insight","simulate","ask","maf_workflow","season","season_run","translate","ui_en"]: sys.modules.pop(_m, None)   # forget old copies from earlier runs
from getpass import getpass
from agents import AzureLLM, pipeline, real_scorecard
from season_run import run_week
if not hasattr(AzureLLM, "translate"):
    raise SystemExit("STOP: GitHub does not have the newest agents.py yet. Upload the new files to the repo first, then run this cell again.")

week = int(input("Which matchweek (1, 2 or 3)? ").strip())
endpoint = input("Endpoint: ").strip()
m_ = re.match(r"(https://[^/]+)", endpoint); endpoint = (m_.group(1) + "/") if m_ else endpoint
deployment = input("Deployment name (gpt-5-mini): ").strip() or "gpt-5-mini"
key = getpass("API key (hidden): ").strip()
llm = AzureLLM(endpoint, key, deployment)
try:
    import maf_workflow
    run_recap = lambda m_, aud, lang: maf_workflow.run(m_, llm, audience=aud, lang=lang)
    print("Orchestration: Microsoft Agent Framework workflow")
except Exception as e:
    print("Agent Framework not available, using the plain pipeline:", str(e)[:200])
    run_recap = lambda m_, aud, lang: pipeline(m_, llm, audience=aud, lang=lang)

OUT = "docs/data"; t0 = time.time()
run_week(week, llm, run_recap, OUT, workers=4, log=lambda *a: print(*a, flush=True))
print(f"\nAll done for matchweek {week} in {int((time.time()-t0)/60)} minutes. Zipping ...")

def make_zip(name, extra=None):
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, fs in os.walk(OUT):
            for f in fs:
                p = os.path.join(root, f)
                if f"mw{week}_" in f or "/ui/" in p: z.write(p, p)
        for p, obj in (extra or {}).items(): z.writestr(p, json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
make_zip(f"matchweek{week}.zip")
try:
    from google.colab import files; files.download(f"matchweek{week}.zip")
except Exception: pass

if input("\nAlso run the planted-mistake test now (about 10 minutes, only needed once)? y/n: ").strip().lower() == "y":
    sc = real_scorecard(llm, n_matches=6, verbose=False)
    names = {"wrong_number": "wrong number", "wrong_team": "swapped team", "invented_cause": "invented cause", "flipped_comparison": "flipped comparison", "wrong_citation": "wrong citation"}
    score = {"source": "measured", "model": deployment, "matches": 6, "planted_errors": sc["planted_errors"], "caught": sc["caught"], "true_sentences": sc["true_sentences"],
             "wrongly_blocked": sc["wrongly_blocked"], "by_kind": {names[k]: v for k, v in sc["by_kind(blocked,total)"].items() if k in names}, "missed_examples": sc["missed_examples"]}
    print(json.dumps(score, indent=1, ensure_ascii=False))
    make_zip(f"matchweek{week}.zip", {"docs/data/scorecard.json": score})
    try: files.download(f"matchweek{week}.zip")
    except Exception: pass
print("DONE")
