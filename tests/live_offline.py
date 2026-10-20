import sys, json; sys.path.insert(0, ".")
from live_ask import handle, MemoryCaps
from agents import MockLLM
caps = MemoryCaps(); env = {"TOTAL_CAP": "3", "IP_PER_HOUR": "2", "ALLOWED_ORIGIN": "https://aniket-padwekar.github.io"}
H = {"origin": "https://aniket-padwekar.github.io", "x-forwarded-for": "1.2.3.4"}
body = lambda q, lang="en", mid="SYN-00101": json.dumps({"match_id": mid, "question": q, "lang": lang}).encode()
mk = lambda: MockLLM(0, 0)
c, h, b = handle("OPTIONS", H, b"", mk, caps, env); print("options", c, h["Access-Control-Allow-Origin"])
c, h, b = handle("POST", H, body("Who scored and when?"), mk, caps, env); print("ask", c, b["status"], b["answer"][:60]); assert c == 200
c, h, b = handle("POST", H, body("Who had the most tackles?", "de"), mk, caps, env); print("ask de", c, b["answer"][:60]); assert c == 200 and b["answer"].startswith("[de]")
c, h, b = handle("POST", H, body("again"), mk, caps, env); print("ip limit", c, b); assert c == 429
H2 = dict(H, **{"x-forwarded-for": "9.9.9.9"})
c, h, b = handle("POST", H2, body("Who scored?"), mk, caps, env); print("other ip", c); assert c == 200
c, h, b = handle("POST", dict(H2, **{"x-forwarded-for": "8.8.8.8"}), body("Who scored?"), mk, caps, env); print("total cap", c, b); assert c == 429
c, h, b = handle("POST", {"origin": "https://evil.example"}, body("x"), mk, MemoryCaps(), env); print("bad origin", c); assert c == 403
c, h, b = handle("POST", H, body("x" * 300), mk, MemoryCaps(), env); print("long", c); assert c == 400
c, h, b = handle("POST", H, body("hi", mid="NOPE"), mk, MemoryCaps(), env); print("unknown match", c); assert c == 404
class Broken:
    def get(self, *a): raise RuntimeError("storage down")
    def add(self, *a): pass
c, h, b = handle("POST", H, body("Who scored?"), mk, Broken(), env); print("storage down ->", c); assert c == 429
print("OK")
