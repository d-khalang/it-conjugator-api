"""Standard Italian forms come out of the built verbs.db (regression: dialect tables used to win, e.g. andare: vò/và)."""
import pytest

from app.db_core import clean_accents, get_conjugations

PERSONS = ["io", "tu", "lui, lei, Lei, egli", "noi", "voi", "loro, Loro, essi"]


def tense(verb, mood, name):
    data = get_conjugations(verb)
    assert data is not None, verb
    return [data["conjugations"][mood][name].get(p) for p in PERSONS]


@pytest.mark.parametrize("verb, forms", [
    ("andare", "vado vai va andiamo andate vanno"),
    ("fare", "faccio fai fa facciamo fate fanno"),
    ("essere", "sono sei è siamo siete sono"),
    ("dare", "do dai dà diamo date danno"),
    ("stare", "sto stai sta stiamo state stanno"),
    ("avere", "ho hai ha abbiamo avete hanno"),
    ("sapere", "so sai sa sappiamo sapete sanno"),
    ("potere", "posso puoi può possiamo potete possono"),
    ("volere", "voglio vuoi vuole vogliamo volete vogliono"),
    ("dovere", "devo devi deve dobbiamo dovete devono"),
    ("venire", "vengo vieni viene veniamo venite vengono"),
    ("tenere", "tengo tieni tiene teniamo tenete tengono"),
    ("dire", "dico dici dice diciamo dite dicono"),
    ("uscire", "esco esci esce usciamo uscite escono"),
    ("bere", "bevo bevi beve beviamo bevete bevono"),
    ("sedere", "siedo siedi siede sediamo sedete siedono"),
    ("valere", "valgo vali vale valiamo valete valgono"),
    ("scegliere", "scelgo scegli sceglie scegliamo scegliete scelgono"),
    ("credere", "credo credi crede crediamo credete credono"),
    ("parlare", "parlo parli parla parliamo parlate parlano"),
    ("partire", "parto parti parte partiamo partite partono"),
    ("finire", "finisco finisci finisce finiamo finite finiscono"),
])
def test_present_indicative_is_standard(verb, forms):
    assert tense(verb, "indicativo", "presente") == forms.split()


@pytest.mark.parametrize("verb, forms", [
    ("essere", "fui fosti fu fummo foste furono"),
    ("fare", "feci facesti fece facemmo faceste fecero"),
    ("mettere", "misi mettesti mise mettemmo metteste misero"),
    ("tacere", "tacqui tacesti tacque tacemmo taceste tacquero"),
    ("potere", "potei potesti poté potemmo poteste poterono"),
    ("rendere", "resi rendesti rese rendemmo rendeste resero"),
])
def test_past_historic_is_standard(verb, forms):
    assert tense(verb, "indicativo", "passato remoto") == forms.split()


@pytest.mark.parametrize("verb, mood, name, forms", [
    ("andare", "indicativo", "futuro semplice", "andrò andrai andrà andremo andrete andranno"),
    ("andare", "congiuntivo", "presente", "vada vada vada andiamo andiate vadano"),
    ("fare", "indicativo", "imperfetto", "facevo facevi faceva facevamo facevate facevano"),
    ("essere", "congiuntivo", "imperfetto", "fossi fossi fosse fossimo foste fossero"),
    ("valere", "condizionale", "presente", "varrei varresti varrebbe varremmo varreste varrebbero"),
])
def test_other_simple_tenses_are_standard(verb, mood, name, forms):
    assert tense(verb, mood, name) == forms.split()


def test_lei_imperative_is_the_third_person_form():
    # a traditional-stress tu form (valùta) is tagged "formal" too and used to land in the Lei slot
    imperative = get_conjugations("valutare")["conjugations"]["imperativo"]["presente"]
    assert (imperative["(tu)"], imperative["(Lei)"], imperative["(Loro)"]) == ("valuta", "valuti", "valutino")


@pytest.mark.parametrize("verb, auxiliary, participle", [
    ("partire", "essere", "partito"),  # "to leave", not the homonym "to divide" (partisco)
    ("fondere", "avere", "fuso"),
    ("notare", "avere", "notato"),  # "to notice", not "alternative form of nuotare"
])
def test_the_main_homonym_wins(verb, auxiliary, participle):
    data = get_conjugations(verb)
    assert (data["auxiliary"], data["principal_forms"]["participio passato"]) == (auxiliary, participle)
    assert data["conjugations"]["indicativo"]["presente"]["noi"].endswith("iamo")


@pytest.mark.parametrize("query, infinitive", [
    ("vado", "andare"), ("va", "andare"), ("vo", "andare"),  # not the archaic gire
    ("fazzo", "fare"), ("fo", "fare"), ("sto", "stare"), ("so", "sapere"),
    ("dico", "dire"), ("mi arrabbio", "arrabbiarsi"),
])
def test_reverse_lookup_prefers_current_verbs(query, infinitive):
    assert get_conjugations(query)["queried"] == infinitive


@pytest.mark.parametrize("verb, io, noi", [
    ("metterci", "ci ho messo", "ci abbiamo messo"),
    ("esserci", "ci sono stato", "ci siamo stati"),
    ("farla", "l'ho fatta", "l'abbiamo fatta"),
    ("farcela", "ce l'ho fatta", "ce l'abbiamo fatta"),
    ("prendersela", "me la sono presa", "ce la siamo presa"),
    ("andarsene", "me ne sono andato", "ce ne siamo andati"),
    ("alzarsi", "mi sono alzato", "ci siamo alzati"),
    ("andare", "sono andato", "siamo andati"),
    ("mangiare", "ho mangiato", "abbiamo mangiato"),
])
def test_compound_tenses_of_clitic_verbs(verb, io, noi):
    perfect = get_conjugations(verb)["conjugations"]["tempi composti"]["passato prossimo"]
    assert (perfect["io"], perfect["noi"]) == (io, noi)


def test_a_clitic_verb_missing_a_person_has_no_compound_for_it():
    perfect = get_conjugations("volerci")["conjugations"]["tempi composti"]["passato prossimo"]
    assert perfect["io"] == "-"
    assert perfect["lui, lei, Lei, egli"] == "ci è voluto"


@pytest.mark.parametrize("raw, clean", [
    ("fà", "fa"), ("và", "va"), ("stò", "sto"), ("fù", "fu"),  # dictionary stress marks
    ("è", "è"), ("dà", "dà"), ("può", "può"), ("già", "già"),  # standard accents stay
    ("andò", "andò"), ("beò", "beò"), ("sdraiò", "sdraiò"), ("città", "città"),
    ("vàdo", "vado"), ("mi arràbbio", "mi arrabbio"),
])
def test_clean_accents(raw, clean):
    assert clean_accents(raw) == clean
