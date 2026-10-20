"""Translation of verified text. The English sentence was already checked against the event log; a translation only has to
keep the same numbers and the same names. It is checked for exactly that, and anything that fails falls back to English."""
import re, json
from agents import numbers_in

LANGS = [("en", "English", "ltr"), ("de", "Deutsch", "ltr"), ("fr", "Français", "ltr"), ("es", "Español", "ltr"), ("it", "Italiano", "ltr"),
         ("pt", "Português", "ltr"), ("nl", "Nederlands", "ltr"), ("pl", "Polski", "ltr"), ("sv", "Svenska", "ltr"), ("da", "Dansk", "ltr"),
         ("fi", "Suomi", "ltr"), ("cs", "Čeština", "ltr"), ("ro", "Română", "ltr"), ("el", "Ελληνικά", "ltr"), ("hu", "Magyar", "ltr"),
         ("tr", "Türkçe", "ltr"), ("ar", "العربية", "rtl"), ("hi", "हिन्दी", "ltr"), ("ja", "日本語", "ltr"), ("zh", "中文", "ltr")]
ENGLISH_NAME = {"de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
                "da": "Danish", "fi": "Finnish", "cs": "Czech", "ro": "Romanian", "el": "Greek", "hu": "Hungarian", "tr": "Turkish", "ar": "Arabic",
                "hi": "Hindi", "ja": "Japanese", "zh": "Simplified Chinese"}
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩०१२३४५६७८९", "01234567890123456789")

def names_in(text, names):
    return [n for n in names if n in text]

def check(src, tr, names):
    """Returns (ok, reason). Same numbers, every name from the source present verbatim, not empty."""
    if not isinstance(tr, str) or not tr.strip(): return False, "empty"
    t = tr.translate(_ARABIC_DIGITS)
    a, b = numbers_in(src), numbers_in(t)
    if a != b: return False, f"numbers differ: {sorted(a)} vs {sorted(b)}"
    miss = [n for n in names_in(src, names) if n not in tr]
    if miss: return False, f"name changed or missing: {miss[:2]}"
    return True, "ok"

def translate_texts(llm, texts, lang, names):
    """-> (translations, fallback_flags). A failed item is retried once on its own, then kept in English."""
    if lang == "en" or not texts: return list(texts), [False] * len(texts)
    out, fb = [None] * len(texts), [False] * len(texts)
    try: first = llm.translate(texts, lang)
    except Exception: first = [None] * len(texts)
    if not isinstance(first, list) or len(first) != len(texts): first = [None] * len(texts)
    for i, s in enumerate(texts):
        cand = first[i]; ok, why = check(s, cand, names)
        if not ok:
            try: cand = llm.translate([s], lang)[0]; ok, why = check(s, cand, names)
            except Exception: ok = False
        if ok: out[i] = cand
        else: out[i], fb[i] = s, True
    return out, fb

PH = re.compile(r"\{[a-z_]+\}")
def translate_ui(llm, ui_en, lang):
    """Interface labels: same placeholders ({player} ...) must survive. Returns (dict, number_of_fallbacks)."""
    keys = list(ui_en); res = {}; bad = 0
    for a in range(0, len(keys), 40):
        chunk = keys[a:a + 40]; src = [ui_en[k] for k in chunk]
        try: tr = llm.translate_ui(src, lang)
        except Exception: tr = [None] * len(src)
        if not isinstance(tr, list) or len(tr) != len(src): tr = [None] * len(src)
        for k, s, t in zip(chunk, src, tr):
            if isinstance(t, str) and t.strip() and sorted(PH.findall(s)) == sorted(PH.findall(t)): res[k] = t
            else: res[k] = s; bad += 1
    return res, bad
