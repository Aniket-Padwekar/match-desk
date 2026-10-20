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

def run_week(week, llm, run_recap, out, langs=None, workers=4, log=print):
    langs = [c for c, _, _ in LANGS if c != "en"] if langs is None else langs
    os.makedirs(f"{out}/lang", exist_ok=True); os.makedirs(f"{out}/ui", exist_ok=True)
    fx = [f for f in fixtures() if f["week"] == week]; packs, names, t0 = {}, {}, time.time()
    for i, f in enumerate(fx, 1):
        m = match_for(f); mid = m["meta"]["match_id"]; names[mid] = names_of(m)
        log(f"[{i}/{len(fx)}] {m['meta']['home']} {m['meta']['final_score']['home']}-{m['meta']['final_score']['away']} {m['meta']['away']}")
        packs[mid] = english_pack(m, llm, run_recap, log)
        log("   recap", packs[mid]["stats"], "| questions", len(packs[mid]["ask"]), f"| {int(time.time()-t0)}s")
        json.dump(packs, open(f"{out}/lang/mw{week}_en.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    def one(code):
        res = {mid: translate_match(p, names[mid], llm, code) for mid, p in packs.items()}
        json.dump(res, open(f"{out}/lang/mw{week}_{code}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        return code, sum(r["fb"] for r in res.values())
    with ThreadPoolExecutor(workers) as ex:
        for code, fb in ex.map(one, langs): log(f"   translated {code}: {fb} items kept in English because the check failed")
    for code in ["en"] + langs:
        p = f"{out}/ui/{code}.json"
        if os.path.exists(p): continue
        if code == "en": ui, bad = dict(UI_EN), 0
        else: ui, bad = translate_ui(llm, UI_EN, code)
        json.dump(ui, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        if bad: log(f"   ui {code}: {bad} labels kept in English")
    return packs
