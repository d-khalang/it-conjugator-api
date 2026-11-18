"""Infinitive index, verb loading, match, suggest and infinitives-only checks (contract §2 Match, §3)."""
from __future__ import annotations

import bisect
import json
import re
import sqlite3
import threading
import unicodedata
import zlib
from functools import lru_cache
from typing import Optional

from ..db_core import DB_PATH, clean_accents, get_conjugations, levenshtein_distance
from .verb import PRONOMINAL_SUFFIXES, build_verb, nfc, pronominal_split

MAX_QUERY_CHARS = 60
MAX_QUERY_WORDS = 4
MAX_CANDIDATES = 5

_lock = threading.Lock()
_index: Optional["_Index"] = None


class _Index:
    """Every infinitive of verbs.db that has a conjugation table, loaded once (~1 s, ~13k names).

    verbs.db also holds ~35k rows without a table (clitic-suffixed forms such as andandoci, alternative
    spellings); they are not verbs for v2. Single-word infinitives are kept sorted for prefix search."""

    def __init__(self) -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            names = []
            for infinitive, blob in conn.execute("SELECT infinitive, conjugation_json FROM verbs"):
                if not blob:
                    continue
                try:
                    table = json.loads(zlib.decompress(blob))
                except (zlib.error, ValueError):
                    continue
                if table.get("indicativo", {}).get("presente"):
                    names.append(nfc(infinitive))
        finally:
            conn.close()
        self.all = frozenset(names)
        self.words = sorted(n for n in names if " " not in n)


def index() -> _Index:
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = _Index()
    return _index


def has_table(infinitive: str) -> bool:
    return infinitive in index().all


def pronominal_of(infinitive: str) -> Optional[tuple[str, str]]:
    return pronominal_split(infinitive, has_table)


def is_infinitive(word: str) -> bool:
    """A single-word verb infinitive: in the table, or a pronominal form of one (lavarsela)."""
    if not word or " " in word:
        return False
    return has_table(word) or pronominal_of(word) is not None


# -- normalisation ----------------------------------------------------------------------------

def normalize(query: str) -> str:
    """NFC, lowercase, trimmed, single spaces, typographic apostrophe -> '."""
    q = unicodedata.normalize("NFC", query).replace("’", "'").replace("‘", "'").lower()
    return " ".join(q.split())


# Contract §3: up to 4 words of letters and apostrophes, single spaces (after normalize()).
VALID_QUERY = re.compile(r"^[a-zàáèéìíòóùú']+( [a-zàáèéìíòóùú']+){0,3}$")


def valid_query(q: str) -> bool:
    return len(q) <= MAX_QUERY_CHARS and VALID_QUERY.fullmatch(q) is not None


# -- verb loading -----------------------------------------------------------------------------

def _raw_table(infinitive: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT conjugation_json FROM verbs WHERE infinitive = ?", (infinitive,)).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    return json.loads(zlib.decompress(row[0]))


@lru_cache(maxsize=512)
def _verb_cached(infinitive: str) -> Optional[str]:
    data = get_conjugations(infinitive)
    if not data or data.get("queried") != infinitive or not data.get("conjugations"):
        return None
    verb = build_verb(infinitive, data, has_table, _raw_table)
    return json.dumps(verb, ensure_ascii=False)


def load_verb(infinitive: str) -> Optional[dict]:
    """The v2 verb object of a single-word infinitive, or None."""
    if not is_infinitive(infinitive):
        return None
    cached = _verb_cached(infinitive)
    return json.loads(cached) if cached else None


def _slot_texts(verb: dict) -> dict[str, list[dict]]:
    """Normalised form text -> slots holding it."""
    out: dict[str, list[dict]] = {}
    for tense in verb["tenses"]:
        for slot in tense["slots"]:
            for form in slot["forms"]:
                ref = {"tense_id": tense["id"], "person": slot["person"]}
                refs = out.setdefault(normalize(form["text"]), [])
                if ref not in refs:
                    refs.append(ref)
    return out


# -- form lookup ------------------------------------------------------------------------------

def _forms_lookup(cursor: sqlite3.Cursor, word: str) -> list[tuple[str, int]]:
    cursor.execute("SELECT infinitive, MIN(priority) FROM forms WHERE form = ? GROUP BY infinitive "
                   "ORDER BY MIN(priority), length(infinitive), infinitive", (word,))
    return cursor.fetchall()


def _infinitives_for_word(cursor: sqlite3.Cursor, word: str) -> list[tuple[str, int]]:
    """Infinitives whose forms include word, best first. One extra hop for participles stored
    as their own entries (andati -> andato -> andare)."""
    variants = [word]
    plain = clean_accents(word)
    if plain != word:
        variants.append(plain)
    m = re.match(r"^(?:[lmtscv]|gl)'(.+)$", word)
    if m:
        variants.append(m.group(1))
    seen: dict[str, int] = {}
    for variant in variants:
        for infinitive, priority in _forms_lookup(cursor, variant):
            infinitive = nfc(infinitive)
            if is_infinitive(infinitive):
                seen.setdefault(infinitive, priority)
            else:
                for inner, inner_priority in _forms_lookup(cursor, infinitive):
                    inner = nfc(inner)
                    if is_infinitive(inner):
                        seen.setdefault(inner, max(priority, inner_priority))
    return sorted(seen.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))


def _pronominal_derivatives(base: str) -> list[str]:
    """Pronominal infinitives built on base that exist (alzare -> alzarsi; andare -> andarsene, andarne...)."""
    stem = base[:-1] if not base.endswith("rre") else base[:-2]
    out = []
    for suffix in PRONOMINAL_SUFFIXES:
        candidate = stem + suffix
        if has_table(candidate):
            out.append(candidate)
    return out


def match(q: str) -> Optional[tuple[dict, dict]]:
    """(match, verb) for a normalised valid query, or None when nothing is close."""
    if " " not in q and is_infinitive(q):
        verb = load_verb(q)
        if verb:
            return {"query": q, "kind": "infinitive", "slots": [], "candidates": []}, verb

    words = q.split(" ")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        found = _infinitives_for_word(cursor, words[-1])
        if not found and len(words) > 1:
            # compound with an auxiliary first and an unknown last word is not a form; try every word
            for word in reversed(words[:-1]):
                found = _infinitives_for_word(cursor, word)
                if found:
                    break
    finally:
        conn.close()

    ordered = [inf for inf, _ in found]
    if len(words) > 1:
        # Proclitics (mi alzo, me ne vado) point to the pronominal verbs of each candidate.
        derived = []
        for inf in ordered:
            base = pronominal_of(inf)
            for d in _pronominal_derivatives(base[0] if base else inf):
                if d not in ordered and d not in derived:
                    derived.append(d)
        ordered = derived + ordered if _has_proclitic(words) else ordered + derived

    hits: list[tuple[str, dict, list[dict]]] = []
    for inf in ordered[:12]:
        verb = load_verb(inf)
        if not verb:
            continue
        slots = _slot_texts(verb).get(q, [])
        if slots:
            hits.append((inf, verb, slots))
    if hits:
        inf, verb, slots = hits[0]
        priority = dict(found)  # derived pronominals are not in it: standard
        # Archaic or regional readings (vado -> gire) are not offered as candidates.
        others = [h[0] for h in hits[1:] if priority.get(h[0], 0) == 0]
        if len(words) == 1:
            others += [i for i, p in found if p == 0 and i != inf and i not in others]
        return {"query": q, "kind": "form", "slots": slots, "candidates": others[:MAX_CANDIDATES]}, verb

    candidates = fuzzy_candidates(q)
    if not candidates:
        return None
    verb = load_verb(candidates[0])
    if not verb:
        return None
    return {"query": q, "kind": "fuzzy", "slots": [], "candidates": candidates}, verb


_PROCLITICS = {"mi", "ti", "si", "ci", "vi", "me", "te", "se", "ce", "ve", "ne", "lo", "la", "li", "le", "gli"}


def _has_proclitic(words: list[str]) -> bool:
    return words[0] in _PROCLITICS or bool(re.match(r"^(?:[mtscv])'", words[0]))


# -- fuzzy and suggest ------------------------------------------------------------------------

def _commonness_key(infinitive: str) -> tuple:
    """Stand-in for word frequency (verbs.db has none): shorter base first, the base before its
    pronominal forms (andare, andarne, andarsene), then alphabetical."""
    split_ = pronominal_of(infinitive)
    base = split_[0] if split_ else infinitive
    return len(base), base, split_ is not None, len(infinitive), infinitive


def fuzzy_candidates(q: str) -> list[str]:
    """Closest infinitives to the query's last word (edit distance ≤ 2, ≤ 1 for short words)."""
    word = clean_accents(q.split(" ")[-1])
    if len(word) < 3:
        return []
    limit = 1 if len(word) <= 4 else 2
    scored: dict[str, int] = {}
    for inf in _prefix_range(word[:1]):
        if abs(len(inf) - len(word)) <= limit:
            d = levenshtein_distance(inf, word)
            if d <= limit:
                scored[inf] = d
    conn = sqlite3.connect(DB_PATH)
    try:
        lo, hi = word[:3], word[:3] + "￿"
        rows = conn.execute("SELECT form, infinitive FROM forms WHERE form >= ? AND form < ? AND priority = 0",
                            (lo, hi)).fetchall()
    finally:
        conn.close()
    for form, inf in rows:
        inf = nfc(inf)
        if abs(len(form) - len(word)) > limit or not is_infinitive(inf):
            continue
        d = levenshtein_distance(clean_accents(nfc(form)), word)
        if d <= limit and d < scored.get(inf, 99):
            scored[inf] = d
    ranked = sorted(scored, key=lambda inf: (scored[inf], _commonness_key(inf)))
    return ranked[:MAX_CANDIDATES]


def _prefix_range(prefix: str) -> list[str]:
    words = index().words
    lo = bisect.bisect_left(words, prefix)
    hi = bisect.bisect_left(words, prefix + "￿")
    return words[lo:hi]


def suggest(q: str, limit: int = 8) -> list[str]:
    q = normalize(q)
    if len(q) < 2 or " " in q:
        return []
    return sorted(_prefix_range(q), key=_commonness_key)[:limit]


def infinitive_or_none(word: str) -> Optional[str]:
    w = normalize(word)
    return w if is_infinitive(w) else None
