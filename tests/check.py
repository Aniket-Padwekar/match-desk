"""Offline regression check used by GitHub Actions: the verifier must never show a wrong sentence and must keep catching planted errors."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents import evaluate, real_scorecard, MockLLM
ev = evaluate(30)
print("recap loop:", ev)
assert ev["wrong_shown"] == 0, "a wrong sentence reached the reader"
sc = real_scorecard(MockLLM(0, 0), n_matches=4, verbose=False)
print("planted errors:", sc)
assert sc["catch_rate_%"] >= 85, "verifier catch rate dropped"
assert sc["false_block_rate_%"] <= 5, "verifier blocks too many true sentences"
print("OK")
