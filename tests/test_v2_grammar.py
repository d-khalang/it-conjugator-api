"""Stem/ending rule (contract §2) and the v2 verb object over common regular and irregular verbs."""
import pytest

from app.v2 import grammar, lexicon
from app.v2.grammar import paradigm, split

COMMON = ["essere", "avere", "andare", "fare", "dare", "stare", "potere", "volere", "dovere", "venire", "dire",
          "uscire", "finire", "cercare", "mangiare", "studiare", "leggere", "scrivere", "prendere",
          "svegliarsi", "andarsene"]


# -- pure rule ---------------------------------------------------------------------------------

@pytest.mark.parametrize("infinitive, present_1s, verb_class, stem", [
    ("parlare", None, "are", "parl"), ("credere", None, "ere", "cred"), ("dormire", "dormo", "ire", "dorm"),
    ("finire", "finisco", "isc", "fin"), ("porre", None, "ere", "pon"), ("tradurre", None, "ere", "traduc"),
    ("trarre", None, "ere", "tra"),
])
def test_paradigm(infinitive, present_1s, verb_class, stem):
    assert paradigm(infinitive, present_1s) == grammar.Paradigm(verb_class, stem)


@pytest.mark.parametrize("infinitive, tense_id, forms", [
    ("cercare", "indicativo-presente", "cerco cerchi cerca cerchiamo cercate cercano"),
    ("pagare", "indicativo-futuro_semplice", "pagherò pagherai pagherà pagheremo pagherete pagheranno"),
    ("mangiare", "indicativo-presente", "mangio mangi mangia mangiamo mangiate mangiano"),
    ("mangiare", "indicativo-futuro_semplice", "mangerò mangerai mangerà mangeremo mangerete mangeranno"),
    ("lasciare", "condizionale-presente", "lascerei lasceresti lascerebbe lasceremmo lascereste lascerebbero"),
    ("studiare", "indicativo-presente", "studio studi studia studiamo studiate studiano"),
    ("studiare", "congiuntivo-presente", "studi studi studi studiamo studiate studino"),
    ("leggere", "indicativo-presente", "leggo leggi legge leggiamo leggete leggono"),
    ("dormire", "indicativo-presente", "dormo dormi dorme dormiamo dormite dormono"),
])
def test_regular_forms_with_spelling_rules(infinitive, tense_id, forms):
    par = paradigm(infinitive)
    assert [par.form(tense_id, i) for i in range(6)] == forms.split()


def test_isc_forms():
    par = paradigm("finire", "finisco")
    assert [par.form("indicativo-presente", i) for i in range(6)] == \
        "finisco finisci finisce finiamo finite finiscono".split()
    assert [par.form("imperativo-presente", i) for i in range(5)] == "finisci finisca finiamo finite finiscano".split()


def parts(infinitive, tense_id, index, form, present_1s=None):
    p = split(paradigm(infinitive, present_1s), tense_id, index, form)
    star = "*" if p["irregular_stem"] or p["irregular_ending"] else ""
    return f"{p['stem']}|{p['ending']}{star}"


@pytest.mark.parametrize("infinitive, tense_id, index, form, expected", [
    # contract §2 examples for andare
    ("andare", "indicativo-presente", 0, "vado", "vad|o*"),
    ("andare", "indicativo-presente", 2, "va", "v|a*"),
    ("andare", "indicativo-presente", 5, "vanno", "vanno|*"),
    ("andare", "indicativo-futuro_semplice", 0, "andrò", "andr|ò*"),
    ("andare", "indicativo-presente", 3, "andiamo", "and|iamo"),
    # spelling changes are not irregular
    ("cercare", "indicativo-presente", 1, "cerchi", "cerch|i"),
    ("cercare", "indicativo-futuro_semplice", 0, "cercherò", "cerch|erò"),
    ("mangiare", "indicativo-futuro_semplice", 3, "mangeremo", "mang|eremo"),
    ("mangiare", "indicativo-presente", 3, "mangiamo", "mang|iamo"),
    ("studiare", "indicativo-presente", 1, "studi", "stud|i"),
    ("dovere", "indicativo-passato_remoto", 0, "dovetti", "dov|etti"),  # regular alternative of dovei
    # irregular
    ("fare", "indicativo-imperfetto", 0, "facevo", "fac|evo*"),
    ("prendere", "indicativo-passato_remoto", 0, "presi", "pres|i*"),
    ("prendere", "indicativo-passato_remoto", 5, "presero", "pres|ero*"),
    ("essere", "indicativo-imperfetto", 0, "ero", "ero|*"),
    ("venire", "condizionale-presente", 0, "verrei", "verr|ei*"),
])
def test_split(infinitive, tense_id, index, form, expected):
    assert parts(infinitive, tense_id, index, form) == expected


def test_split_isc():
    assert parts("finire", "indicativo-presente", 0, "finisco", "finisco") == "fin|isco"
    assert parts("finire", "indicativo-presente", 5, "finiscono", "finisco") == "fin|iscono"


# -- whole verbs from verbs.db ------------------------------------------------------------------

def form_text(form):
    p = form["parts"]
    if p["kind"] == "simple":
        joined = p["stem"] + p["ending"] + (p["enclitic"] or "")
        if p["clitic"]:
            joined = p["clitic"] + joined if p["clitic"].endswith("'") else f"{p['clitic']} {joined}"
        return joined
    aux = f"{p['auxiliary']} {p['participle']}"
    if p["clitic"]:
        aux = p["clitic"] + aux if p["clitic"].endswith("'") else f"{p['clitic']} {aux}"
    return aux


@pytest.mark.parametrize("infinitive", COMMON + ["farcela", "esserci", "volerci", "prendersela", "porre"])
def test_verb_object_invariants(infinitive):
    verb = lexicon.load_verb(infinitive)
    assert verb and verb["infinitive"] == infinitive
    ids = [t["id"] for t in verb["tenses"]]
    assert ids == [i for i in grammar.TENSE_IDS if i in ids]
    for tense in verb["tenses"]:
        assert any(slot["forms"] for slot in tense["slots"])
        assert tense["id"] == f"{tense['mood']}-{tense['tense']}"
        expected_persons = grammar.IMP_PERSONS if tense["mood"] == "imperativo" else grammar.PERSONS
        assert [s["person"] for s in tense["slots"]] == expected_persons
        for slot in tense["slots"]:
            if not slot["forms"]:
                continue
            assert sum(f["primary"] for f in slot["forms"]) == 1 and slot["forms"][0]["primary"]
            for form in slot["forms"]:
                assert "/" not in form["text"] and "(" not in form["text"]
                assert form["tts"] == form["text"]
                assert form["parts"]["kind"] == ("compound" if tense["compound"] else "simple")
                assert form_text(form) == form["text"], form


@pytest.mark.parametrize("infinitive, irregular, auxiliary, pronominal", [
    ("essere", True, "essere", None), ("avere", True, "avere", None), ("finire", False, "avere", None),
    ("cercare", False, "avere", None), ("mangiare", False, "avere", None), ("studiare", False, "avere", None),
    ("svegliarsi", False, "essere", "si"), ("andarsene", True, "essere", "sene"), ("scrivere", True, "avere", None),
])
def test_verb_flags(infinitive, irregular, auxiliary, pronominal):
    verb = lexicon.load_verb(infinitive)
    assert verb["irregular"] is irregular and verb["pronominal"] == pronominal
    assert verb["auxiliaries"] == [{"verb": auxiliary, "primary": True, "note": None}]


def slot(verb, tense_id, person):
    tense = next(t for t in verb["tenses"] if t["id"] == tense_id)
    return next(s for s in tense["slots"] if s["person"] == person)["forms"]


def test_essere_compounds_have_a_feminine_variant():
    forms = slot(lexicon.load_verb("svegliarsi"), "indicativo-passato_prossimo", "1p")
    assert [(f["text"], f["tags"]) for f in forms] == [("ci siamo svegliati", []), ("ci siamo svegliate", ["feminine"])]
    assert forms[0]["parts"]["clitic"] == "ci" and forms[0]["parts"]["auxiliary"] == "siamo"


def test_avere_compounds_have_no_gender_variant_and_flag_irregular_participles():
    forms = slot(lexicon.load_verb("scrivere"), "indicativo-passato_prossimo", "1s")
    assert [f["text"] for f in forms] == ["ho scritto"]
    assert forms[0]["parts"]["irregular_participle"] and forms[0]["irregular"]


def test_object_clitic_compounds_agree_with_the_object_not_the_subject():
    forms = slot(lexicon.load_verb("farcela"), "indicativo-passato_prossimo", "1s")
    assert [f["text"] for f in forms] == ["ce l'ho fatta"]
    assert forms[0]["parts"]["clitic"] == "ce l'" and forms[0]["parts"]["auxiliary"] == "ho"


def test_reflexive_clitic_parts():
    form = slot(lexicon.load_verb("svegliarsi"), "indicativo-presente", "1s")[0]
    assert form["parts"] == {"kind": "simple", "clitic": "mi", "stem": "svegli", "ending": "o", "enclitic": None,
                             "irregular_stem": False, "irregular_ending": False}


def enclitic_parts(infinitive, person):
    form = slot(lexicon.load_verb(infinitive), "imperativo-presente", person)[0]
    p = form["parts"]
    return f"{p['stem']}|{p['ending']}|{p['enclitic']}", p["clitic"], form["irregular"]


@pytest.mark.parametrize("infinitive, person, expected, irregular", [
    ("svegliarsi", "2s", "svegli|a|ti", False),
    ("svegliarsi", "1p", "svegl|iamo|ci", False),
    ("svegliarsi", "2p", "svegli|ate|vi", False),
    ("andarsene", "2s", "v|a|ttene", True),  # short base va', doubled consonant in the enclitic
    ("andarsene", "1p", "and|iamo|cene", False),
    ("andarsene", "2p", "and|ate|vene", False),
])
def test_enclitic_imperatives(infinitive, person, expected, irregular):
    assert enclitic_parts(infinitive, person) == (expected, None, irregular)


def test_proclitic_imperative_has_no_enclitic():
    assert enclitic_parts("svegliarsi", "3s") == ("svegl|i|None", "si", False)


def test_defective_slots_are_empty_and_empty_tenses_are_omitted():
    volerci = lexicon.load_verb("volerci")
    assert slot(volerci, "indicativo-presente", "1s") == []
    assert slot(volerci, "indicativo-presente", "3s")[0]["text"] == "ci vuole"
    assert "imperativo-presente" not in [t["id"] for t in lexicon.load_verb("potere")["tenses"]]


def test_missing_principal_form_is_null():
    assert lexicon.load_verb("essere")["principal_forms"]["present_participle"] is None


# -- match -------------------------------------------------------------------------------------

@pytest.mark.parametrize("query, infinitive, kind, slots", [
    ("andare", "andare", "infinitive", []),
    ("svegliarsi", "svegliarsi", "infinitive", []),
    ("vado", "andare", "form", [("indicativo-presente", "1s")]),
    ("andiamo", "andare", "form", [("indicativo-presente", "1p"), ("congiuntivo-presente", "1p"),
                                   ("imperativo-presente", "1p")]),
    ("sono andato", "andare", "form", [("indicativo-passato_prossimo", "1s")]),
    ("siamo andate", "andare", "form", [("indicativo-passato_prossimo", "1p"), ("congiuntivo-passato", "1p")]),
    ("mi alzo", "alzarsi", "form", [("indicativo-presente", "1s")]),
    ("me ne vado", "andarsene", "form", [("indicativo-presente", "1s")]),
    ("ce l'ho fatta", "farcela", "form", [("indicativo-passato_prossimo", "1s")]),
    ("vattene", "andarsene", "form", [("imperativo-presente", "2s")]),
    ("va'", "andare", "form", [("imperativo-presente", "2s")]),
    ("andrò", "andare", "form", [("indicativo-futuro_semplice", "1s")]),
    ("finisco", "finire", "form", [("indicativo-presente", "1s")]),
    ("ho scritto", "scrivere", "form", [("indicativo-passato_prossimo", "1s")]),
    ("andre", "andare", "fuzzy", []),
])
def test_match(query, infinitive, kind, slots):
    match, verb = lexicon.match(lexicon.normalize(query))
    assert verb["infinitive"] == infinitive
    assert match["kind"] == kind and match["query"] == lexicon.normalize(query)
    assert [(s["tense_id"], s["person"]) for s in match["slots"]] == slots


def test_match_candidates_leave_out_archaic_readings():
    match, _ = lexicon.match("vado")
    assert match["candidates"] == ["andarsene"]  # not the archaic gire


def test_normalize():
    assert lexicon.normalize("  Me  NE  Vado ") == "me ne vado"
    assert lexicon.normalize("ce l’ho fatta") == "ce l'ho fatta"


def test_pronominal_derivatives_use_every_clitic_suffix():
    assert {"smetterla"} <= set(lexicon._pronominal_derivatives("smettere"))
    assert {"prenderle", "prendersela"} <= set(lexicon._pronominal_derivatives("prendere"))


@pytest.mark.parametrize("query, infinitive", [("la smetto", "smetterla"), ("le prendo", "prenderle")])
def test_match_object_clitic_verbs(query, infinitive):
    match, verb = lexicon.match(query)
    assert (match["kind"], verb["infinitive"]) == ("form", infinitive)
    assert ("indicativo-presente", "1s") in [(s["tense_id"], s["person"]) for s in match["slots"]]


@pytest.mark.parametrize("query, ok", [
    ("vado", True), ("me ne vado", True), ("ce l'ho fatta", True), ("a b c d", True),
    (" vado", False), ("vado ", False), ("vado  via", False), ("a b c d e", False), ("", False), ("x" * 61, False),
])
def test_valid_query_is_the_contract_rule(query, ok):
    assert lexicon.valid_query(query) is ok


def test_curated_variant_equal_to_the_data_is_not_duplicated(monkeypatch):
    from app.v2 import verb as verb_module
    monkeypatch.setitem(verb_module.EXTRA_VARIANTS, ("dire", "imperativo-presente", "2s"), [("di'", [])])
    lexicon._verb_cached.cache_clear()
    try:
        assert [f["text"] for f in slot(lexicon.load_verb("dire"), "imperativo-presente", "2s")] == ["di'"]
    finally:
        lexicon._verb_cached.cache_clear()
