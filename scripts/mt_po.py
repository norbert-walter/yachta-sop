#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mt_po.py — Machine Translation für Sphinx-PO-Kataloge mit Google Translate (v2, API-Key),
inkl. reST-Masking, Plural-Support, Batching/Throttle und optionaler Nachbearbeitung
(Capitalize-First oder Title-Case für Überschriften).

ENV-Variablen:
  GOOGLE_API_KEY          # dein Google Cloud Translation API-Key (v2, Basic)
  TARGET_LANG=en          # Zielsprache (ISO/BCP-47, z. B. en, fr, es, zh_CN, zh-CN). Default: de
  REWRITE_FUZZY=true      # fuzzy-Einträge neu befüllen (Default: true)
  REWRITE_FILLED=false    # bereits gefüllte, nicht-fuzzy Einträge überschreiben (Default: false)
  DNT=Foo,Bar             # Kommagetrennte „Do Not Translate“-Phrasen (optional)
  BATCH_SIZE=128          # max. 128 Texte/Request (Default: 128)
  THROTTLE_SECONDS=0.0    # Pause zwischen Requests in Sekunden (Default: 0.0)

  POSTPROCESS=none|capitalize_first|title_case   # Nachbearbeitung (Default: none)
  POSTPROCESS_LANGS=en,fr                        # Für welche Zielsprachen anwenden (Default: en)
  HEADING_MAX_LEN=70                             # Heuristik-Grenze für Title-Case (Default: 70)

Aufruf (im Workflow mit working-directory=docs):
  python ../scripts/mt_po.py
oder explizit:
  python scripts/mt_po.py docs/locale/<TARGET_LANG>/LC_MESSAGES
"""
import os
import sys
import re
import html
import time
import requests
import polib
import string
from itertools import islice
from typing import Dict, List, Tuple

# --------------------- Konfiguration aus ENV ---------------------
TARGET_LANG      = os.getenv("TARGET_LANG", "de").strip()
REWRITE_FUZZY    = os.getenv("REWRITE_FUZZY", "true").lower() == "true"
REWRITE_FILLED   = os.getenv("REWRITE_FILLED", "false").lower() == "true"
DNT_LIST         = [s.strip() for s in os.getenv("DNT", "").split(",") if s.strip()]
BATCH_SIZE       = int(os.getenv("BATCH_SIZE", "128"))
THROTTLE_SECONDS = float(os.getenv("THROTTLE_SECONDS", "0"))

# Nachbearbeitung (optional)
POSTPROCESS       = os.getenv("POSTPROCESS", "none").strip().lower()   # none | capitalize_first | title_case
POSTPROCESS_LANGS = {s.strip().lower() for s in os.getenv("POSTPROCESS_LANGS", "en").split(",") if s.strip()}
HEADING_MAX_LEN   = int(os.getenv("HEADING_MAX_LEN", "70"))

# --------------------- Utilities ---------------------
def chunked(iterable, n):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk

def need_nplurals(po: polib.POFile) -> int:
    m = re.search(r"nplurals\s*=\s*(\d+)", po.metadata.get("Plural-Forms", "") or "")
    return int(m.group(1)) if m else 2

# ---- Sprach-Helper ----
def normalize_sphinx_lang(tag: str) -> str:
    """
    Normalisiert eine Sprachkennung für Sphinx/Dateipfade:
      - Bindestrich -> Unterstrich
      - Sprache lower-case, Region upper-case
    Beispiele:
      'zh-CN'/'zh_cn'/'ZH-cn' -> 'zh_CN'
      'pt-br' -> 'pt_BR'
      'de'    -> 'de'
    """
    t = (tag or "").replace("-", "_")
    parts = t.split("_")
    if len(parts) == 2 and parts[1]:
        return f"{parts[0].lower()}_{parts[1].upper()}"
    return parts[0].lower()

def google_target_code(tag: str) -> str:
    """
    Liefert einen BCP-47-Code für die Google API:
      - Unterstrich -> Bindestrich
      - Sprache lower-case, Region upper-case
    Beispiele:
      'zh_CN' -> 'zh-CN'
      'pt_br' -> 'pt-BR'
      'de'    -> 'de'
    """
    t = (tag or "").replace("_", "-")
    parts = t.split("-")
    if len(parts) == 2 and parts[1]:
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return parts[0].lower()

# --------------------- Google v2 (API key) ---------------------
def google_translate_batch(texts: List[str], target: str) -> List[str]:
    """Übersetzt eine Liste von Strings (max. ~128) in einem Request."""
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY missing")
    url = "https://translation.googleapis.com/language/translate/v2"
    payload = {"q": texts, "target": target, "format": "text"}
    try:
        r = requests.post(url, params={"key": key}, json=payload, timeout=60)
        if r.status_code >= 400:
            # Response enthält hilfreiche Fehlerdetails (quotaExceeded, billingNotEnabled, etc.)
            raise RuntimeError(f"Google Translate v2 error {r.status_code}: {r.text[:500]}")
        data = r.json()
        outs = [html.unescape(t["translatedText"]) for t in data["data"]["translations"]]
        return outs
    except requests.RequestException as ex:
        raise RuntimeError(f"HTTP error calling Google Translate v2: {ex}")
# --------------------- RTD-/reST-spezifische Behandlung ---------------------
RTD_REF_RE = re.compile(r"`([^`]+)`_")
RTD_TARGET_RE = re.compile(r"(?m)^_([^:\n]+):\s*(\S+)\s*$")

def rtd_preprocess(s: str):
    items = []
    out = s
    def repl_ref(m):
        inner = m.group(1)
        key = f"[[RTDREF{len(items)}]]"
        if "<" in inner and ">" in inner:
            items.append(("ref_explicit", key, m.group(0)))
            return key
        else:
            items.append(("ref", key, inner))
            return key
    out = RTD_REF_RE.sub(repl_ref, out)
    def repl_target(m):
        name = m.group(1).strip()
        url = m.group(2).strip()
        key = f"[[RTDTARGET{len(items)}]]"
        items.append(("target", key, name, url))
        return key
    out = RTD_TARGET_RE.sub(repl_target, out)
    return out, items

def rtd_reconstruct(s_translated: str, items):
    out = s_translated
    for it in items:
        kind = it[0]
        if kind == "ref_explicit":
            _, key, original = it
            out = out.replace(key, original)
        elif kind == "ref":
            _, key, name_tr = it
            out = out.replace(key, f"`{name_tr}`_")
        elif kind == "target":
            _, key, name_tr, url = it
            out = out.replace(key, f"_{name_tr}: {url}")
    return out

def mask_text_generic(s: str):
    table = {}
    i = 0
    def sub_all(pats, txt):
        nonlocal i
        for pat in pats:
            def repl(m):
                nonlocal i
                k = f"[[[[M{i}]]]]"
                table[k] = m.group(0)
                i += 1
                return k
            txt = pat.sub(repl, txt)
        return txt
    s2 = sub_all(MASK_PATTERNS, s)
    if DNT_PATTERNS:
        s2 = sub_all(DNT_PATTERNS, s2)
    return s2, table

def translate_one_rtd_aware(src: str) -> str:
    base, items = rtd_preprocess(src)
    masked, table = mask_text_generic(base)
    main_tr = google_translate_batch([masked], google_target_code(TARGET_LANG))[0]
    translated_items = []
    for it in items:
        kind = it[0]
        if kind == "ref":
            _, key, name = it
            name_tr = google_translate_batch([name], google_target_code(TARGET_LANG))[0]
            name_tr = postprocess_text(name_tr, name)
            translated_items.append(("ref", key, name_tr))
        elif kind == "target":
            _, key, name, url = it
            name_tr = google_translate_batch([name], google_target_code(TARGET_LANG))[0]
            name_tr = postprocess_text(name_tr, name)
            translated_items.append(("target", key, name_tr, url))
        else:
            translated_items.append(it)
    demasked = unmask_text(main_tr, table)
    final = rtd_reconstruct(demasked, translated_items)
    final = postprocess_text(final, src)
    return final


# --------------------- Masking für reST & Platzhalter ---------------------
MASK_PATTERNS: List[re.Pattern] = [
    re.compile(r"``[^`]+``"),                # inline code
    re.compile(r":[\w.-]+:`[^`]+`"),         # :role:`...`
    # re.compile(r"`[^`]+`_"),              # NICHT hier maskieren; RTD-Logik übernimmt
    # Fett/Kursiv NICHT maskieren, damit Inhalt übersetzt wird:
    # re.compile(r"\*\*[^*\n]+\*\*"),        # **bold**
    # re.compile(r"\*[^*\s][^*\n]*\*"),      # *italic*
    re.compile(r"\|[^|\n]+\|"),              # |subst|
    # Platzhalter:
    re.compile(r"%\([^)]+\)[#0\- +]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diouxXeEfFgGcrs%]"),
    re.compile(r"%(?:\d+\$)?[diouxXeEfFgGcrs%]"),
    re.compile(r"\{[^\{\}\n]+\}"),
]

def build_dnt_patterns(lst: List[str]) -> List[re.Pattern]:
    return [re.compile(re.escape(p)) for p in lst]

DNT_PATTERNS = build_dnt_patterns(DNT_LIST)

def mask_text(s: str) -> Tuple[str, Dict[str, str]]:
    table: Dict[str, str] = {}
    i = 0
    def sub_all(pats: List[re.Pattern], txt: str) -> str:
        nonlocal i
        for pat in pats:
            def repl(m):
                nonlocal i
                k = f"[[[[M{i}]]]]"
                table[k] = m.group(0)
                i += 1
                return k
            txt = pat.sub(repl, txt)
        return txt
    s = sub_all(MASK_PATTERNS, s)
    if DNT_PATTERNS:
        s = sub_all(DNT_PATTERNS, s)
    return s, table

def unmask_text(s: str, table: Dict[str, str]) -> str:
    for k, v in table.items():
        s = s.replace(k, v)
    return s

def translate_many_preserving_markup(texts: List[str]) -> List[str]:
    """Maskiert jeden Text, übersetzt im Batch, und demaskiert wieder."""
    masked, tables = [], []
    for t in texts:
        m, tab = mask_text(t)
        masked.append(m)
        tables.append(tab)
    # Nutze BCP-47-Zielcode für Google (z. B. 'zh-CN', 'pt-BR')
    outs = google_translate_batch(masked, google_target_code(TARGET_LANG))
    return [unmask_text(o, tab) for o, tab in zip(outs, tables)]

# --------------------- Nachbearbeitung (Groß-/Kleinschreibung) ---------------------
LOWER_WORDS = {
    "a","an","the","and","but","or","nor","for","so","yet",
    "at","by","in","of","on","to","up","with","as","from","over","per"
}

def capitalize_first_alpha(s: str) -> str:
    """Ersten alphabetischen Buchstaben groß setzen, Markup/Whitespace davor ignorieren."""
    chars = list(s)
    for i, ch in enumerate(chars):
        if ch.isalpha():
            chars[i] = ch.upper()
            break
    return "".join(chars)

def split_punct(word: str) -> Tuple[str, str, str]:
    """Zerlegt ein Wort in prefix-punct, core, suffix-punct (z. B. '“hello,”' -> ('“','hello',',”'))."""
    start = 0
    end = len(word)
    # erweiterte Anführungszeichen berücksichtigen
    quotes = "„“‚’«»‹›"
    while start < end and word[start] in string.punctuation + quotes:
        start += 1
    while end > start and word[end-1] in string.punctuation + quotes:
        end -= 1
    return word[:start], word[start:end], word[end:]

def looks_like_heading(src: str) -> bool:
    s = src.strip()
    return (len(s) > 0) and (len(s) <= HEADING_MAX_LEN) and ("\n" not in s) and (s.count(".") == 0)

def smart_title_case(s: str) -> str:
    """Very-light Title Case: erste/letzte Wörter groß, sonst Stoppwörter klein."""
    words = s.split()
    if not words:
        return s
    out = []
    last_idx = len(words) - 1
    for i, w in enumerate(words):
        prefix, core, suffix = split_punct(w)
        if not core:
            out.append(w)
            continue
        lc = core.lower()
        if i == 0 or i == last_idx or lc not in LOWER_WORDS:
            core_tc = core[:1].upper() + core[1:]
        else:
            core_tc = lc
        out.append(prefix + core_tc + suffix)
    return " ".join(out)

def postprocess_text(translated: str, src_msgid: str) -> str:
    """Wendet die gewählte Nachbearbeitung auf den übersetzten Text an (abhängig von Sprache & Modus)."""
    if TARGET_LANG.lower() not in POSTPROCESS_LANGS:
        return translated
    if POSTPROCESS == "capitalize_first":
        return capitalize_first_alpha(translated)
    if POSTPROCESS == "title_case":
        if looks_like_heading(src_msgid):
            return smart_title_case(translated)
        # Fallback: wenigstens ersten Buchstaben groß
        return capitalize_first_alpha(translated)
    return translated

# --------------------- PO-Logik ---------------------
def should_translate_entry(e: polib.POEntry) -> bool:
    if not e.msgid.strip():
        return False
    has_translation = bool(e.msgstr.strip()) if not e.msgid_plural else any((v or "").strip() for v in e.msgstr_plural.values())
    is_fuzzy = "fuzzy" in (e.flags or [])
    if not has_translation:
        return True
    if is_fuzzy and REWRITE_FUZZY:
        return True
    if REWRITE_FILLED:
        return True
    return False

def process_plural(e: polib.POEntry, nplurals: int) -> bool:
    """Einfacher Plural: Index 0 aus msgid, alle weiteren aus msgid_plural."""
    changed = False
    for i in range(nplurals):
        current = e.msgstr_plural.get(i, "")
        if current.strip() and not REWRITE_FILLED and not ("fuzzy" in e.flags and REWRITE_FUZZY):
            continue
        src = e.msgid if i == 0 else (e.msgid_plural or e.msgid)
        tr = translate_one_rtd_aware(src)
        if e.msgstr_plural.get(i, "") != tr:
            e.msgstr_plural[i] = tr
            changed = True
    if "fuzzy" not in e.flags:
        e.flags.append("fuzzy")
        changed = True or changed
    return changed

def process_po_file(path: str) -> bool:
    po = polib.pofile(path)
    npl = need_nplurals(po)
    changed = False

    # 1) Plural-Einträge separat behandeln (der Einfachheit halber aktuell einzeln)
    for e in po:
        if e.msgid_plural and should_translate_entry(e):
            if process_plural(e, npl):
                changed = True

    # 2) Singuläre Einträge einzeln RTD-bewusst übersetzen
    pending_entries: List[polib.POEntry] = [e for e in po if not e.msgid_plural and should_translate_entry(e)]
    total = len(pending_entries)
    if total:
        print(f"Translating {total} singular entries in {path} (RTD-aware)")
    for e in pending_entries:
        tr = translate_one_rtd_aware(e.msgid)
        if e.msgstr != tr:
            e.msgstr = tr
            changed = True
        if "fuzzy" not in e.flags:
            e.flags.append("fuzzy")
            changed = True
        if THROTTLE_SECONDS > 0:
            time.sleep(THROTTLE_SECONDS)

    if changed:
        po.save(path)
        print(f"Updated {path}")
    return changed

def default_po_dir() -> str:
    """
    Standard-Verzeichnis relativ zum aktuellen Arbeitsverzeichnis (z. B. docs/):
      locale/<lang>_<REGION>/LC_MESSAGES
    Sprach-Tag wird robust normalisiert, damit sowohl 'zh-CN' als auch 'zh_CN'
    zum gleichen Pfad 'zh_CN' führen.
    """
    norm = normalize_sphinx_lang(TARGET_LANG)
    return os.path.join("locale", norm, "LC_MESSAGES")

# --------------------- Main ---------------------
if __name__ == "__main__":
    po_dir = sys.argv[1] if len(sys.argv) > 1 else default_po_dir()
    if not os.path.isdir(po_dir):
        sys.stderr.write(f"PO directory not found: {po_dir}\n")
        sys.exit(2)
    print(f"Google v2 MT for {TARGET_LANG} in {po_dir} (REWRITE_FUZZY={REWRITE_FUZZY}, REWRITE_FILLED={REWRITE_FILLED}, BATCH_SIZE={BATCH_SIZE}, THROTTLE_SECONDS={THROTTLE_SECONDS}, POSTPROCESS={POSTPROCESS}, POSTPROCESS_LANGS={','.join(sorted(POSTPROCESS_LANGS))})")

    for root, _, files in os.walk(po_dir):
        for fn in files:
            if fn.endswith(".po"):
                process_po_file(os.path.join(root, fn))

