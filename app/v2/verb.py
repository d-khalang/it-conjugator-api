"""Builds the v2 verb object (contract §2) from the v1 table that db_core returns."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from . import grammar
from .grammar import IMP_PERSONS, PERSONS, TENSES

# Build date of verbs.db (contract: informative). Bump it whenever verbs.db is rebuilt.
DATA_VERSION = "2026-11-13"

V1_PERSONS = ["io", "tu", "lui, lei, Lei, egli", "noi", "voi", "loro, Loro, essi"]
V1_IMP_PERSONS = ["(tu)", "(Lei)", "(noi)", "(voi)", "(Loro)"]

# v1 (mood, tense) for each canonical tense id
V1_TENSE = {
    "indicativo-presente": ("indicativo", "presente"),
    "indicativo-imperfetto": ("indicativo", "imperfetto"),
    "indicativo-passato_remoto": ("indicativo", "passato remoto"),
    "indicativo-futuro_semplice": ("indicativo", "futuro semplice"),
    "indicativo-passato_prossimo": ("tempi composti", "passato prossimo"),
    "indicativo-trapassato_prossimo": ("tempi composti", "trapassato prossimo"),
    "indicativo-trapassato_remoto": ("tempi composti", "trapassato remoto"),
    "indicativo-futuro_anteriore": ("tempi composti", "futuro anteriore"),
    "congiuntivo-presente": ("congiuntivo", "presente"),
    "congiuntivo-imperfetto": ("congiuntivo", "imperfetto"),
    "congiuntivo-passato": ("congiuntivo", "passato"),
    "congiuntivo-trapassato": ("congiuntivo", "trapassato"),
    "condizionale-presente": ("condizionale", "presente"),
    "condizionale-passato": ("condizionale", "passato"),
    "imperativo-presente": ("imperativo", "presente"),
}

# Clitic suffixes of pronominal infinitives, longest first (svegliarsi -> si, andarsene -> sene).
PRONOMINAL_SUFFIXES = ("sene", "sela", "sele", "selo", "seli", "cela", "cele", "celo", "celi", "cene",
                       "si", "ci", "ne", "vi", "la", "lo", "le", "li", "gli")
# Clitic suffixes whose object pronoun sets the participle agreement (no gender variant then).
OBJECT_AGREEMENT = {"la", "lo", "le", "li", "sela", "sele", "selo", "seli", "cela", "cele", "celo", "celi"}

# Variants the data doesn't carry yet: standard truncated tu-imperatives (contract fixture: va').
# (base infinitive, tense_id, person) -> [(text, tags)]
EXTRA_VARIANTS: dict[tuple[str, str, str], list[tuple[str, list[str]]]] = {
    ("andare", "imperativo-presente", "2s"): [("va'", [])],
    ("dare", "imperativo-presente", "2s"): [("da'", [])],
    ("fare", "imperativo-presente", "2s"): [("fa'", [])],
    ("stare", "imperativo-presente", "2s"): [("sta'", [])],
}

_EMPTY = {"", "-", "—"}
_ELIDED = re.compile(r"^((?:[lmtscv]|gl)')(.+)$")  # l'ho -> l' + ho


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def pronominal_split(infinitive: str, exists) -> Optional[tuple[str, str]]:
    """(base infinitive, clitic suffix) for a pronominal infinitive, else None. exists(inf) -> bool."""
    if " " in infinitive:
        return None
    for suffix in PRONOMINAL_SUFFIXES:
        if infinitive.endswith(suffix):
            stem = infinitive[: -len(suffix)]
            if not stem.endswith("r") or len(stem) < 3:
                continue
            for base in (stem + "e", stem + "re"):
                if base != infinitive and exists(base):
                    return base, suffix
    return None


def _split_clitic(text: str) -> tuple[Optional[str], str]:
    """'me ne vado' -> ('me ne', 'vado'); "ce l'ho" -> ("ce l'", 'ho'); 'vado' -> (None, 'vado')."""
    words = text.split(" ")
    clitic_words, last = words[:-1], words[-1]
    m = _ELIDED.match(last)
    if m and (clitic_words or len(m.group(2)) > 1):
        joined = " ".join(clitic_words + [m.group(1)]) if clitic_words else m.group(1)
        return joined, m.group(2)
    return (" ".join(clitic_words) or None), last


def join_clitic(clitic: Optional[str], rest: str) -> str:
    if not clitic:
        return rest
    return clitic + rest if clitic.endswith("'") else f"{clitic} {rest}"


class _Builder:
    def __init__(self, infinitive: str, data: dict, base: str, suffix: Optional[str],
                 base_table: Optional[dict]):
        self.infinitive = infinitive
        self.data = data
        self.conj = data["conjugations"]
        self.base = base
        self.suffix = suffix
        self.base_table = base_table  # the base verb's v1 table, for enclitic imperatives
        present_1s = self._v1("indicativo-presente", "io")
        _, present_1s = _split_clitic(present_1s) if present_1s else (None, None)
        self.par = grammar.paradigm(base, present_1s)
        self.auxiliary = data.get("auxiliary") or "avere"
        self.irregular = False

    def _v1(self, tense_id: str, v1_person: str, table: Optional[dict] = None) -> Optional[str]:
        mood, tense = V1_TENSE[tense_id]
        value = (table or self.conj).get(mood, {}).get(tense, {}).get(v1_person)
        if value is None or value.strip() in _EMPTY:
            return None
        return nfc(value.strip())

    # -- simple forms ------------------------------------------------------------------------
    def _simple(self, tense_id: str, index: int, person: str, v1_person: str, text: str,
                primary: bool, tags: list[str]) -> dict:
        clitic, rest = _split_clitic(text)
        enclitic = None
        if clitic is None and self.suffix and tense_id == "imperativo-presente" and self.base_table:
            # Enclitic imperative (svegliati, vattene): split the base form (sveglia, va); the rest of the
            # text, doubled consonant included, is the enclitic.
            base_form = self._enclitic_base(tense_id, index, v1_person, text)
            if base_form:
                rest, enclitic = base_form, text[len(base_form):]
        parts = grammar.split(self.par, tense_id, index, rest)
        irregular = not self.par.is_regular(tense_id, index, rest)
        self.irregular |= irregular
        return self._form(text, primary, tags, irregular, {
            "kind": "simple", "clitic": clitic, "stem": parts["stem"], "ending": parts["ending"],
            "enclitic": enclitic, "irregular_stem": parts["irregular_stem"],
            "irregular_ending": parts["irregular_ending"]})

    def _enclitic_base(self, tense_id: str, index: int, v1_person: str, text: str) -> Optional[str]:
        """The base verb's form that text starts with: its own form (sveglia) or a short one (va' -> va)."""
        base_form = self._v1(tense_id, v1_person, self.base_table)
        if not base_form or " " in base_form:
            return None
        person = IMP_PERSONS[index]
        options = [base_form.rstrip("'")] + [v.rstrip("'") for v, _ in EXTRA_VARIANTS.get((self.base, tense_id, person), [])]
        fits = [o for o in options if text.startswith(o) and len(text) > len(o)]
        return max(fits, key=len) if fits else None

    @staticmethod
    def _form(text, primary, tags, irregular, parts) -> dict:
        return {"text": text, "primary": primary, "tags": tags, "tts": text, "irregular": irregular,
                "parts": parts}

    # -- compound forms ----------------------------------------------------------------------
    def _compound(self, text: str, person: str) -> list[dict]:
        head, participle = text.rsplit(" ", 1)
        clitic, auxiliary = _split_clitic(head)
        masc = self._masculine_participle(participle)
        irregular_pp = masc != self.par.participle
        self.irregular |= irregular_pp

        def make(pp: str, primary: bool, tags: list[str]) -> dict:
            full = join_clitic(clitic, f"{auxiliary} {pp}")
            return self._form(full, primary, tags, irregular_pp, {
                "kind": "compound", "clitic": clitic, "auxiliary_verb": self.auxiliary,
                "auxiliary": auxiliary, "participle": pp, "irregular_participle": irregular_pp})

        forms = [make(participle, True, [])]
        if self.auxiliary == "essere" and self.suffix not in OBJECT_AGREEMENT and participle[-1:] in ("o", "i"):
            feminine = participle[:-1] + ("a" if person.endswith("s") else "e")
            forms.append(make(feminine, False, ["feminine"]))
        return forms

    def _masculine_participle(self, participle: str) -> str:
        pp = self.data["principal_forms"].get("participio passato") or participle
        pp = nfc(pp)
        if self.suffix and pp.endswith(self.suffix):
            pp = pp[: -len(self.suffix)]
        return pp if pp[-1:] == "o" else participle[:-1] + "o"

    # -- whole verb --------------------------------------------------------------------------
    def build(self) -> dict:
        tenses = []
        for mood, tense, compound in TENSES:
            tense_id = f"{mood}-{tense}"
            persons, v1_persons = (IMP_PERSONS, V1_IMP_PERSONS) if mood == "imperativo" else (PERSONS, V1_PERSONS)
            slots, any_form = [], False
            for index, (person, v1_person) in enumerate(zip(persons, v1_persons)):
                text = self._v1(tense_id, v1_person)
                forms: list[dict] = []
                if text:
                    if compound:
                        forms = self._compound(text, person)
                    else:
                        forms = [self._simple(tense_id, index, person, v1_person, text, True, [])]
                        for extra, tags in EXTRA_VARIANTS.get((self.infinitive, tense_id, person), []):
                            if any(f["text"] == extra for f in forms):
                                continue  # the data already has it
                            forms.append(self._simple(tense_id, index, person, v1_person, extra, False, tags))
                any_form |= bool(forms)
                slots.append({"person": person, "forms": forms})
            if any_form:
                tenses.append({"id": tense_id, "mood": mood, "tense": tense, "compound": compound, "slots": slots})

        pf = self.data["principal_forms"]

        def principal(key: str) -> Optional[str]:
            value = (pf.get(key) or "").strip()
            return None if value in _EMPTY else nfc(value)

        return {
            "infinitive": self.infinitive,
            "pronominal": self.suffix,
            "auxiliaries": [{"verb": self.auxiliary, "primary": True, "note": None}],
            "principal_forms": {"gerund": principal("gerundio"), "past_participle": principal("participio passato"),
                                "present_participle": principal("participio presente")},
            "irregular": self.irregular,
            "data_version": DATA_VERSION,
            "tenses": tenses,
        }


def build_verb(infinitive: str, data: dict[str, Any], exists, base_table_of) -> dict:
    """data: the v1 dict from db_core.get_conjugations(infinitive).
    exists(inf) -> bool; base_table_of(inf) -> v1 conjugations dict or None."""
    split_ = pronominal_split(infinitive, exists)
    base, suffix = split_ if split_ else (infinitive.split(" ")[0], None)
    base_table = base_table_of(base) if suffix else None
    return _Builder(infinitive, data, base, suffix, base_table).build()
