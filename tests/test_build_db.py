"""build_db reads the standard conjugation table of a Wiktionary (kaikki.org) entry."""
from build_db import extract_conjugations_and_metadata, is_modern_entry, is_primary_entry

PRESENT = [("first-person", "singular"), ("second-person", "singular"), ("singular", "third-person"),
           ("first-person", "plural"), ("plural", "second-person"), ("plural", "third-person")]


def table(forms, extra_tags=()):
    """One it-conj table: its markers, then the present indicative forms given."""
    rows = [{"form": "irregular", "tags": ["table-tags"], "source": "conjugation"},
            {"form": "it-conj", "tags": ["inflection-template"], "source": "conjugation"}]
    for form, person in zip(forms.split(), PRESENT):
        rows.append({"form": form, "tags": ["indicative", "present", *person, *extra_tags], "source": "conjugation"})
    return rows


def present(entry):
    _, _, _, conjugations, has_conjugations = extract_conjugations_and_metadata(entry)
    assert has_conjugations
    return " ".join(conjugations["indicativo"]["presente"].values())


def test_only_the_first_table_counts():
    # andare's page has a second table with archaic and regional forms, mostly untagged
    entry = {"word": "andare", "forms": table("vàdo vài và andiàmo andàte vànno") + table("vò vài và andiàmo andàte vànno")}
    assert present(entry) == "vado vai va andiamo andate vanno"


def test_the_first_form_of_a_slot_wins_and_marked_forms_come_last():
    forms = table("fàccio fài fà facciàmo fàte fànno")
    forms.insert(2, {"form": "fò", "tags": ["archaic", "first-person", "indicative", "present", "singular"],
                     "source": "conjugation"})
    assert present({"word": "fare", "forms": forms}) == "faccio fai fa facciamo fate fanno"


def test_a_marked_form_is_used_when_it_is_the_only_one():
    assert present({"word": "x", "forms": table("a b c d e f", extra_tags=["literary"])}) == "a b c d e f"


def test_lei_imperative_needs_a_third_person_form():
    forms = [{"form": "it-conj", "tags": ["inflection-template"], "source": "conjugation"},
             {"form": "vàluta", "tags": ["imperative", "second-person", "singular"], "source": "conjugation"},
             {"form": "valùta", "tags": ["Traditional", "formal", "imperative", "second-person", "singular"], "source": "conjugation"},
             {"form": "vàluti", "tags": ["formal", "imperative", "second-person-semantically", "singular", "third-person"], "source": "conjugation"}]
    _, _, _, conjugations, _ = extract_conjugations_and_metadata({"word": "valutare", "forms": forms})
    assert conjugations["imperativo"]["presente"] == {"(tu)": "valuta", "(Lei)": "valuti"}


def test_primary_and_modern_entries():
    alternative = {"senses": [{"tags": ["alt-of", "alternative"], "alt_of": [{"word": "nuotare"}]}]}
    archaic = {"senses": [{"tags": ["archaic", "dialectal", "literary"], "glosses": ["to go"]}]}
    current = {"senses": [{"glosses": ["to notice"]}]}

    assert not is_primary_entry(alternative) and is_primary_entry(archaic) and is_primary_entry(current)
    assert not is_modern_entry(alternative) and not is_modern_entry(archaic) and is_modern_entry(current)
