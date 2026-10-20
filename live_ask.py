"""Live 'Ask the match' backend logic (no Azure Functions imports here, so it can be tested offline).
The Azure Function in function_app.py is a thin wrapper around handle()."""
import os, json, time, hashlib, logging, functools

MAX_Q = 200
log = logging.getLogger("matchdesk")

class MemoryCaps:
    """Offline stand-in for the Table Storage counters."""
    def __init__(self): self.d = {}
    def get(self, pk, rk): return self.d.get((pk, rk), 0)
    def add(self, pk, rk): self.d[(pk, rk)] = self.get(pk, rk) + 1

class TableCaps:
    """Counters in the Function App's own storage account (Azure Table), so the cap survives restarts and several instances."""
    def __init__(self, conn):
        from azure.data.tables import TableServiceClient
        self.t = TableServiceClient.from_connection_string(conn).create_table_if_not_exists("caps")
    def get(self, pk, rk):
        from azure.core.exceptions import ResourceNotFoundError
        try: return int(self.t.get_entity(pk, rk).get("n", 0))
        except ResourceNotFoundError: return 0
    def add(self, pk, rk):
        from azure.core.exceptions import ResourceNotFoundError
        from azure.data.tables import UpdateMode
        from azure.core import MatchConditions
        for _ in range(5):
            try:
                e = self.t.get_entity(pk, rk); e["n"] = int(e.get("n", 0)) + 1
                self.t.update_entity(e, mode=UpdateMode.REPLACE, etag=e.metadata["etag"], match_condition=MatchConditions.IfNotModified); return
            except ResourceNotFoundError:
                try: self.t.create_entity({"PartitionKey": pk, "RowKey": rk, "n": 1}); return
                except Exception: continue
            except Exception: continue

def cors(origin_ok):
    return {"Access-Control-Allow-Origin": origin_ok, "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin"}

@functools.lru_cache(maxsize=64)
def match_by_id(mid):
    from season import fixtures, match_for
    for f in fixtures():
        if f"SYN-{f['seed']:05d}" == mid: return match_for(f)
    return None

def names_of(m):
    me = m["meta"]; out = {me["home"], me["away"]}
    for sd in ("home", "away"):
        for p in me["lineups"][sd]["players"] + me["lineups"][sd]["bench"]: out.add(p["name"])
    return sorted(out, key=len, reverse=True)

def client_key(headers):
    ip = (headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or "unknown").split(",")[0].split(":")[0].strip()
    return hashlib.sha256((os.environ.get("IP_SALT", "md") + ip).encode()).hexdigest()[:16]

def handle(method, headers, body, llm_factory, caps, env=None):
    """-> (status_code, headers, json_body). Never raises."""
    env = env or os.environ; allowed = env.get("ALLOWED_ORIGIN", "https://aniket-padwekar.github.io")
    origin = headers.get("origin") or headers.get("Origin") or ""
    h = cors(allowed if origin == allowed else allowed)
    if method == "OPTIONS": return 204, h, None
    if origin and origin != allowed and not origin.startswith("http://localhost") and not origin.startswith("http://127.0.0.1"):
        return 403, h, {"error": "origin"}
    if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"): h = cors(origin)
    try: req = json.loads(body or b"{}")
    except Exception: return 400, h, {"error": "bad json"}
    q = str(req.get("question", "")).strip(); mid = str(req.get("match_id", "")); lang = str(req.get("lang", "en"))[:5]
    if not q or len(q) > MAX_Q: return 400, h, {"error": "question length"}
    m = match_by_id(mid)
    if m is None: return 404, h, {"error": "unknown match"}
    cap, per_hour = int(env.get("TOTAL_CAP", 300)), int(env.get("IP_PER_HOUR", 12))
    ck, hour = client_key(headers), time.strftime("%Y%m%d%H")
    try:
        if caps.get("total", "all") >= cap: return 429, h, {"error": "cap"}
        if caps.get("ip", f"{ck}-{hour}") >= per_hour: return 429, h, {"error": "rate"}
        caps.add("total", "all"); caps.add("ip", f"{ck}-{hour}")
    except Exception as e:
        log.error("cap store failed: %s", e); return 429, h, {"error": "cap"}   # fail closed: never spend money without a working counter
    t0 = time.time()
    try:
        from ask import answer
        llm = llm_factory(); r = answer(m, q, llm)
        out = {"status": r["status"], "answer": r["answer"], "sentences": [{"text": s["text"], "receipts": s.get("receipts", [])} for s in r["sentences"]], "trace": r["trace"]}
        if lang != "en":
            from translate import translate_texts
            texts = [s["text"] for s in out["sentences"]] or [out["answer"]]
            tr, fb = translate_texts(llm, texts, lang, names_of(m))
            if out["sentences"]:
                for s, t in zip(out["sentences"], tr): s["text"] = t
            out["answer"] = " ".join(tr)
            out["translated"] = not all(fb)
        log.info("ask_ok %s", json.dumps({"match": mid, "status": out["status"], "secs": round(time.time() - t0, 1), "lang": lang, "steps": [x["agent"] for x in out["trace"]]}))
        return 200, h, out
    except Exception as e:
        log.error("ask_failed %s", str(e)[:300]); return 500, h, {"error": "failed"}
