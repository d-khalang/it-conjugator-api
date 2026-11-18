"""Regular Italian paradigms and the stem/ending split (contract §2, "Stem and ending").

Pure and deterministic: no database access. The reference implementation for andare is
docs/verbs/make_fixtures.py in the app repo; this module generalises it to every verb class.
"""
from __future__ import annotations

from dataclasses import dataclass

PERSONS = ["1s", "2s", "3s", "1p", "2p", "3p"]
IMP_PERSONS = ["2s", "3s", "1p", "2p", "3p"]

# (mood, tense, compound) in canonical order (contract §1).
TENSES = [
    ("indicativo", "presente", False), ("indicativo", "imperfetto", False),
    ("indicativo", "passato_remoto", False), ("indicativo", "futuro_semplice", False),
    ("indicativo", "passato_prossimo", True), ("indicativo", "trapassato_prossimo", True),
    ("indicativo", "trapassato_remoto", True), ("indicativo", "futuro_anteriore", True),
    ("congiuntivo", "presente", False), ("congiuntivo", "imperfetto", False),
    ("congiuntivo", "passato", True), ("congiuntivo", "trapassato", True),
    ("condizionale", "presente", False), ("condizionale", "passato", True),
    ("imperativo", "presente", False),
]
TENSE_IDS = [f"{m}-{t}" for m, t, _ in TENSES]

# Regular endings per class and simple tense, in person order (imperativo: 2s..3p).
ENDINGS: dict[str, dict[str, list[str]]] = {
    "are": {
        "indicativo-presente": ["o", "i", "a", "iamo", "ate", "ano"],
        "indicativo-imperfetto": ["avo", "avi", "ava", "avamo", "avate", "avano"],
        "indicativo-passato_remoto": ["ai", "asti", "ò", "ammo", "aste", "arono"],
        "indicativo-futuro_semplice": ["erò", "erai", "erà", "eremo", "erete", "eranno"],
        "congiuntivo-presente": ["i", "i", "i", "iamo", "iate", "ino"],
        "congiuntivo-imperfetto": ["assi", "assi", "asse", "assimo", "aste", "assero"],
        "condizionale-presente": ["erei", "eresti", "erebbe", "eremmo", "ereste", "erebbero"],
        "imperativo-presente": ["a", "i", "iamo", "ate", "ino"],
    },
    "ere": {
        "indicativo-presente": ["o", "i", "e", "iamo", "ete", "ono"],
        "indicativo-imperfetto": ["evo", "evi", "eva", "evamo", "evate", "evano"],
        "indicativo-passato_remoto": ["ei", "esti", "é", "emmo", "este", "erono"],
        "indicativo-futuro_semplice": ["erò", "erai", "erà", "eremo", "erete", "eranno"],
        "congiuntivo-presente": ["a", "a", "a", "iamo", "iate", "ano"],
        "congiuntivo-imperfetto": ["essi", "essi", "esse", "essimo", "este", "essero"],
        "condizionale-presente": ["erei", "eresti", "erebbe", "eremmo", "ereste", "erebbero"],
        "imperativo-presente": ["i", "a", "iamo", "ete", "ano"],
    },
    "ire": {
        "indicativo-presente": ["o", "i", "e", "iamo", "ite", "ono"],
        "indicativo-imperfetto": ["ivo", "ivi", "iva", "ivamo", "ivate", "ivano"],
        "indicativo-passato_remoto": ["ii", "isti", "ì", "immo", "iste", "irono"],
        "indicativo-futuro_semplice": ["irò", "irai", "irà", "iremo", "irete", "iranno"],
        "congiuntivo-presente": ["a", "a", "a", "iamo", "iate", "ano"],
        "congiuntivo-imperfetto": ["issi", "issi", "isse", "issimo", "iste", "issero"],
        "condizionale-presente": ["irei", "iresti", "irebbe", "iremmo", "ireste", "irebbero"],
        "imperativo-presente": ["i", "a", "iamo", "ite", "ano"],
    },
}
ENDINGS["isc"] = {
    **ENDINGS["ire"],
    "indicativo-presente": ["isco", "isci", "isce", "iamo", "ite", "iscono"],
    "congiuntivo-presente": ["isca", "isca", "isca", "iamo", "iate", "iscano"],
    "imperativo-presente": ["isci", "isca", "iamo", "ite", "iscano"],
}

# Core endings beyond the class endings, per tense and person: they split irregular forms
# (andrò = andr|ò, misi = mis|i). Taken from the reference, plus the strong passato remoto.
_EXTRA_CORE: dict[str, list[list[str]]] = {
    "indicativo-presente": [["o"], ["i"], ["a", "e"], ["iamo"], ["ate", "ete", "ite"], ["ano", "ono"]],
    "indicativo-passato_remoto": [["i", "etti"], [], ["e", "è", "ette"], [], [], ["ero", "ettero"]],
    "indicativo-futuro_semplice": [["ò"], ["ai"], ["à"], ["emo"], ["ete"], ["anno"]],
    "congiuntivo-presente": [["i", "a"], ["i", "a"], ["i", "a"], ["iamo"], ["iate"], ["ino", "ano"]],
    "condizionale-presente": [["ei"], ["esti"], ["ebbe"], ["emmo"], ["este"], ["ebbero"]],
    "imperativo-presente": [["a", "i", "e"], ["i", "a"], ["iamo"], ["ate", "ete", "ite"], ["ino", "ano"]],
}


def core_endings(tense_id: str, index: int) -> set[str]:
    """Every class's regular ending for this slot plus the extra core endings."""
    out = {ENDINGS[c][tense_id][index] for c in ENDINGS}
    extra = _EXTRA_CORE.get(tense_id)
    if extra:
        out.update(extra[index])
    return out


# Regular alternatives to the class ending (credei / credetti): not irregular.
ALTERNATE_ENDINGS: dict[tuple[str, str], list[list[str]]] = {
    ("ere", "indicativo-passato_remoto"): [["etti"], [], ["ette"], [], [], ["ettero"]],
}

REGULAR_PARTICIPLE = {"are": "ato", "ere": "uto", "ire": "ito", "isc": "ito"}


@dataclass(frozen=True)
class Paradigm:
    """The regular paradigm of a base (non-pronominal) infinitive."""
    verb_class: str  # are | ere | ire | isc
    stem: str

    def slot_stem(self, ending: str) -> str:
        """The stem as spelled before this ending (cerc+i -> cerch, mangi+erò -> mang, studi+i -> stud)."""
        stem, first = self.stem, ending[:1]
        if self.verb_class != "are" or first not in ("e", "i", "è", "é", "ì"):
            return stem
        if stem.endswith(("c", "g")):
            return stem + "h"
        if stem.endswith(("ci", "gi")):
            return stem[:-1]
        if stem.endswith("i") and first in ("i", "ì"):
            return stem[:-1]
        return stem

    def ending(self, tense_id: str, index: int) -> str:
        return ENDINGS[self.verb_class][tense_id][index]

    def regular_endings(self, tense_id: str, index: int) -> list[str]:
        """The class ending first, then its regular alternatives."""
        alternates = ALTERNATE_ENDINGS.get((self.verb_class, tense_id))
        return [self.ending(tense_id, index), *(alternates[index] if alternates else [])]

    def form(self, tense_id: str, index: int) -> str:
        ending = self.ending(tense_id, index)
        return self.slot_stem(ending) + ending

    def is_regular(self, tense_id: str, index: int, form: str) -> bool:
        return any(self.slot_stem(e) + e == form for e in self.regular_endings(tense_id, index))

    @property
    def participle(self) -> str:
        return self.stem + REGULAR_PARTICIPLE[self.verb_class]


def paradigm(base_infinitive: str, present_1s: str | None = None) -> Paradigm:
    """Class and stem of a base infinitive. present_1s (without clitics) tells -isc- verbs apart."""
    inf = base_infinitive
    if inf.endswith("urre"):
        return Paradigm("ere", inf[:-4] + "uc")  # tradurre: traduc-
    if inf.endswith("orre"):
        return Paradigm("ere", inf[:-4] + "on")  # porre: pon-
    if inf.endswith("arre"):
        return Paradigm("ere", inf[:-4] + "a")  # trarre: tra-
    stem, suffix = inf[:-3], inf[-3:]
    if suffix == "are":
        return Paradigm("are", stem)
    if suffix == "ire":
        isc = present_1s is not None and present_1s == stem + "isco"
        return Paradigm("isc" if isc else "ire", stem)
    return Paradigm("ere", stem)


def split(par: Paradigm, tense_id: str, index: int, form: str) -> dict:
    """SimpleParts (without clitic) of one form: the longest fitting candidate ending wins."""
    regular = par.regular_endings(tense_id, index)
    regular_ending = regular[0]
    candidates = core_endings(tense_id, index) | set(regular)
    fits = [e for e in candidates if form.endswith(e) and len(form) > len(e)]
    ending = max(fits, key=lambda e: (len(e), e)) if fits else ""
    stem = form[: len(form) - len(ending)]
    return {
        "stem": stem,
        "ending": ending,
        "irregular_stem": stem != par.slot_stem(regular_ending),
        "irregular_ending": ending not in regular,
    }
