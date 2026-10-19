# Colab cell: tests 'Ask the Match' (chat over a match) with your real Azure model.
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
from ask import answer, QUESTIONS
from insight import why_result
if not hasattr(AzureLLM, 'plan'):
    raise SystemExit('STOP: GitHub still has the OLD agents.py (no Judge agent). Upload the new agents.py to the repo first, then run this cell again.')

endpoint = input("Endpoint: ").strip()
m_ = re.match(r"(https://[^/]+)", endpoint); endpoint = (m_.group(1) + "/") if m_ else endpoint
deployment = input("Deployment name (gpt-5-mini): ").strip() or "gpt-5-mini"
key = getpass("API key (hidden): ").strip()
llm = AzureLLM(endpoint, key, deployment)


rows = []
for seed in (24, 47):
    m = simulate(seed); print(f'\n##### Match: {m["meta"]["home"]} {m["meta"]["final_score"]["home"]}-{m["meta"]["final_score"]["away"]} {m["meta"]["away"]}')
    for q, can in QUESTIONS:
        t0 = time.time()
        try: r = answer(m, q, llm)
        except Exception as e: print("FAILED", q, str(e)[:200]); continue
        r["expected_answerable"] = can; r["seed"] = seed; rows.append(r)
        mark = "OK " if (r["status"] == "answered") == can else "BAD"
        print(f'{mark} [{r["status"]}] {q}\n     -> {r["answer"][:300]}   ({round(time.time()-t0)}s)')
ans = [r for r in rows if r["expected_answerable"]]; un = [r for r in rows if not r["expected_answerable"]]
sc = {"answerable_questions": len(ans), "answered": sum(r["status"] == "answered" for r in ans),
      "unanswerable_questions": len(un), "correctly_refused": sum(r["status"] == "cannot_tell" for r in un),
      "blocked_sentences": sum(1 for r in rows for t in r["trace"] if "blocked" in t["event"])}
print("\nSUMMARY", json.dumps(sc))
json.dump({"summary": sc, "rows": rows}, open("ask_results.json", "w"), ensure_ascii=False, indent=1)
try:
    from google.colab import files; files.download("ask_results.json")
except Exception: pass
