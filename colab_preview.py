# Colab cell: quick preview (about 3 minutes). Writes the new recap for 2 matches and 3 answers so we can check the wording BEFORE the long runs.
!pip -q install openai
!pip -q install --pre agent-framework
!rm -rf match-desk && git clone -q https://github.com/Aniket-Padwekar/match-desk.git
import sys, re
sys.path.insert(0, "match-desk")
for _m in ["agents","engine","insight","simulate","ask","maf_workflow","season","translate","ui_en"]: sys.modules.pop(_m, None)
from getpass import getpass
from agents import AzureLLM, pipeline
from ask import answer
from season import fixtures, match_for
endpoint = input("Endpoint: ").strip()
m_ = re.match(r"(https://[^/]+)", endpoint); endpoint = (m_.group(1) + "/") if m_ else endpoint
deployment = input("Deployment name (gpt-5-mini): ").strip() or "gpt-5-mini"
llm = AzureLLM(endpoint, getpass("API key (hidden): ").strip(), deployment)
try:
    import maf_workflow; run = lambda m: maf_workflow.run(m, llm, audience="fan", lang="English")
except Exception: run = lambda m: pipeline(m, llm, audience="fan", lang="English")
fx = [f for f in fixtures() if f["week"] == 1]
for i in (3, 5):
    m = match_for(fx[i]); out = run(m)
    print("\n=== ", out["headline"], " ===")
    for s in out["sentences"]: print(" -", s["text"])
    print("   stats:", out["stats"])
m = match_for(fx[3])
for q in ["What formation did the away team play?", "Which player was rated highest and why?", "How many fouls did the away team commit?"]:
    r = answer(m, q, llm); print("\nQ:", q, "\nA:", r["status"], "-", r["answer"])
