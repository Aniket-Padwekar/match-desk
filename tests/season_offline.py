import sys, os, json, shutil; sys.path.insert(0, ".")
from agents import MockLLM, pipeline
from season_run import run_week
llm = MockLLM(0, 0); out = "/tmp/claude-0/season_test"; shutil.rmtree(out, ignore_errors=True)
p = run_week(1, llm, lambda m, a, l: pipeline(m, llm, audience=a, lang=l), out, langs=["de", "ar", "ja"], log=lambda *a: None)
print(len(p), sorted(os.listdir(out + "/lang")), sorted(os.listdir(out + "/ui")))
d = json.load(open(out + "/lang/mw1_de.json")); k = list(d)[0]; print(d[k]["h"], d[k]["s"][:1], str(d[k]["a"][:2])[:200], d[k]["fb"])
