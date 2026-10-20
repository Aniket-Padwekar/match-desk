# Colab cell: quick (about 2 minutes) check that the Microsoft Agent Framework workflow runs with your Azure model.
!pip -q install openai
!pip -q install --pre agent-framework
!rm -rf match-desk && git clone -q https://github.com/Aniket-Padwekar/match-desk.git
import sys, re
sys.path.insert(0, "match-desk")
for _m in ["agents","engine","insight","simulate","ask","maf_workflow"]: sys.modules.pop(_m, None)
from getpass import getpass
from simulate import simulate
from agents import AzureLLM
import maf_workflow
endpoint = input("Endpoint: ").strip()
m_ = re.match(r"(https://[^/]+)", endpoint); endpoint = (m_.group(1) + "/") if m_ else endpoint
deployment = input("Deployment name (gpt-5-mini): ").strip() or "gpt-5-mini"
llm = AzureLLM(endpoint, getpass("API key (hidden): ").strip(), deployment)
out = maf_workflow.run(simulate(1), llm, audience="fan")
print(out["headline"]); print(out["stats"])
for s in out["sentences"]: print(" -", s["text"])
print("\nAgent steps:", [t["agent"] for t in out["trace"]])
print("OK: the Agent Framework workflow ran end to end.")
