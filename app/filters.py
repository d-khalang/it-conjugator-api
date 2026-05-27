from __future__ import annotations
from collections import OrderedDict
from typing import Dict, Any


def _to_set(csv: str | None) -> set[str] | None:
    if not csv:
        return None
    return {p.strip().lower() for p in csv.split(",") if p.strip()}


def apply_filters(data: Dict[str, Any], moods: str | None, tenses: str | None, persons: str | None, full: bool) -> Dict[str, Any]:
    """Return filtered copy; preserves original order of keys."""
    if full:
        return data

    mset = _to_set(moods)
    tset = _to_set(tenses)
    pset = _to_set(persons)

    conj = data.get("conjugations", {})
    new_conj: Dict[str, Any] = {}

    for mood, tenses_map in conj.items():
        if mset and mood.lower() not in mset:
            continue
        new_tenses_map: Dict[str, Any] = {}
        for tense, person_map in tenses_map.items():
            if tset and tense.lower() not in tset:
                continue
            if pset:
                filtered_person_map = OrderedDict(
                    (p, f) for p, f in person_map.items() if p.lower() in pset
                )
            else:
                filtered_person_map = person_map
            if filtered_person_map:
                new_tenses_map[tense] = filtered_person_map
        if new_tenses_map:
            new_conj[mood] = new_tenses_map

    new_data = dict(data)
    new_data["conjugations"] = new_conj
    return new_data