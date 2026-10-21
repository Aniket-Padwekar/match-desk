"""Generates the model-written part of one matchweek: English recaps + answers, then the checked translations in 19 languages.
Output goes to <out>/lang/mw{n}_{code}.json (and <out>/ui/{code}.json once). Used by colab_season.py (real model) and by the offline test (mock)."""
import json, os, time
from concurrent.futures import ThreadPoolExecutor
from season import fixtures, match_for
from ask import answer, QUESTIONS_SITE
from translate import LANGS, translate_texts, translate_ui
from ui_en import UI_EN

def names_of(m):
    me = m["meta"]; out = {me["home"], me["away"]}
    for sd in ("home", "away"):
        for p in me["lineups"][sd]["players"] + me["lineups"][sd]["bench"]: out.add(p["name"])
    return sorted(out, key=len, reverse=True)

def english_pack(m, llm, run_recap, log=print):
    rec = run_recap(m, "fan", "English")
    for s in rec["sentences"]: s.pop("_mutated", None)
    pack = {"headline": rec["headline"], "sentences": [{k: s.get(k) for k in ("text", "fact_ids", "status", "receipts")} for s in rec["sentences"]],
            "trace": rec["trace"], "stats": rec["stats"], "ask": []}
    for q, can in QUESTIONS_SITE:
        try: r = answer(m, q, llm)
        except Exception as e:
            log("   ask failed:", q, str(e)[:120]); r = {"question": q, "status": "cannot_tell", "answer": "The match data cannot tell us this.", "sentences": [], "trace": []}
        pack["ask"].append({"status": r["status"], "answer": r["answer"], "sentences": [{"text": s["text"], "receipts": s.get("receipts", [])} for s in r["sentences"]], "trace": r["trace"]})
    return pack

def flatten(pack):
    """All English strings that need translating, in a fixed order, plus how to put them back."""
    texts = [pack["headline"]] + [s["text"] for s in pack["sentences"]]
    for a in pack["ask"]:
        if a["status"] == "answered" and a["sentences"]: texts += [s["text"] for s in a["sentences"]]
        else: texts.append(a["answer"])
    return texts

def unflatten(pack, tr):
    it = iter(tr); out = {"h": next(it), "s": [next(it) for _ in pack["sentences"]], "a": []}
    for a in pack["ask"]:
        if a["status"] == "answered" and a["sentences"]: out["a"].append([next(it) for _ in a["sentences"]])
        else: out["a"].append(next(it))
    return out

def translate_match(pack, names, llm, code, chunk=30):
    texts = flatten(pack); tr = []; fb = 0
    for i in range(0, len(texts), chunk):
        t, f = translate_texts(llm, texts[i:i + chunk], code, names); tr += t; fb += sum(f)
    res = unflatten(pack, tr); res["fb"] = fb; return res

def run_week(week, llm, run_recap, out, langs=None, workers=6, log=print):
    """Matches run in parallel (recap + 11 answers each), then every (language, match) translation runs in parallel."""
    langs = [c for c, _, _ in LANGS if c != "en"] if langs is None else langs
    os.makedirs(f"{out}/lang", exist_ok=True); os.makedirs(f"{out}/ui", exist_ok=True)
    fx = [f for f in fixtures() if f["week"] == week]; t0 = time.time(); matches = [match_for(f) for f in fx]
    names = {m["meta"]["match_id"]: names_of(m) for m in matches}
    def gen(m):
        mid = m["meta"]["match_id"]; p = english_pack(m, llm, run_recap, log)
        log(f"   done {m['meta']['home']} {m['meta']['final_score']['home']}-{m['meta']['final_score']['away']} {m['meta']['away']} | recap {p['stats']} | {int(time.time()-t0)}s")
        return mid, p
    packs = {}
    with ThreadPoolExecutor(workers) as ex:
        for mid, p in ex.map(gen, matches): packs[mid] = p
    json.dump(packs, open(f"{out}/lang/mw{week}_en.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"English done in {int((time.time()-t0)/60)} min. Translating into {len(langs)} languages ...")
    jobs = [(c, mid) for c in langs for mid in packs]; res = {c: {} for c in langs}; fbs = {c: 0 for c in langs}
    def tr(job):
        c, mid = job; r = translate_match(packs[mid], names[mid], llm, c); return c, mid, r
    with ThreadPoolExecutor(workers) as ex:
        for c, mid, r in ex.map(tr, jobs): res[c][mid] = r; fbs[c] += r["fb"]
    for c in langs:
        json.dump(res[c], open(f"{out}/lang/mw{week}_{c}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        log(f"   translated {c}: {fbs[c]} items kept in English because the check failed")
    for code in ["en"] + langs:   # interface labels: translate only the labels that are missing from the existing file
        p = f"{out}/ui/{code}.json"
        cur = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        if code == "en": cur = dict(UI_EN)
        else:
            miss = {k: v for k, v in UI_EN.items() if k not in cur}
            if miss:
                t_, bad = translate_ui(llm, miss, code); cur.update(t_)
                if bad: log(f"   ui {code}: {bad} labels kept in English")
        json.dump({k: cur.get(k, UI_EN[k]) for k in UI_EN}, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"Matchweek {week} finished in {int((time.time()-t0)/60)} minutes.")
    return packs
