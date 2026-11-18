"""v2 routes against the contract fixtures (copied from docs/verbs/fixtures/conjugator in the app repo)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import api

FIXTURES = Path(__file__).parent / "fixtures" / "conjugator"
KEY = {"X-API-Key": "test-key"}


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "test-key")
    return TestClient(api.app)


def test_vado_reproduces_the_fixture_exactly(client):
    r = client.get("/v2/conjugate", params={"q": "vado"}, headers=KEY)
    assert r.status_code == 200
    assert r.json() == fixture("conjugate-vado.json")


def test_fuzzy_query_returns_the_same_verb_as_the_fixture(client):
    expected = fixture("conjugate-fuzzy.json")
    body = client.get("/v2/conjugate", params={"q": "andre"}, headers=KEY).json()
    assert body["verb"] == expected["verb"]
    assert body["match"]["kind"] == "fuzzy" and body["match"]["slots"] == []
    # candidates are ranked by edit distance; the fixture lists two of them as an example
    assert body["match"]["candidates"][0] == "andare"


def test_not_found(client):
    r = client.get("/v2/conjugate", params={"q": "qwerty"}, headers=KEY)
    assert r.status_code == 404
    assert r.json() == fixture("conjugate-not-found.json")


def test_infinitives_only(client):
    r = client.post("/v2/infinitives", json=fixture("infinitives-request.json"), headers=KEY)
    assert r.json() == fixture("infinitives-response.json")


def test_infinitives_rejects_more_than_500_words(client):
    r = client.post("/v2/infinitives", json={"words": ["andare"] * 501}, headers=KEY)
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_many_words"


@pytest.mark.parametrize("word, expected", [
    ("andarsene", "andarsene"), ("Andare", "andare"), ("porta", None), ("sale", None), ("letto", None),
    ("vado", None), ("andare via", None), ("", None),
])
def test_infinitives_words(client, word, expected):
    body = client.post("/v2/infinitives", json={"words": [word]}, headers=KEY).json()
    assert body["infinitives"] == {word: expected}


def test_suggest_shape_and_order(client):
    items = client.get("/v2/suggest", params={"q": "and"}, headers=KEY).json()["items"]
    # the fixture's three verbs, base before its pronominal forms; andarne is a real verb with a table
    assert items == ["andare", "andarne", "andarsene", "andicappare"]
    assert set(fixture("suggest-and.json")["items"]) <= set(items)


@pytest.mark.parametrize("q", ["a", "", " "])
def test_suggest_short_query_is_empty(client, q):
    assert client.get("/v2/suggest", params={"q": q}, headers=KEY).json() == {"items": []}


def test_suggest_limit(client):
    assert len(client.get("/v2/suggest", params={"q": "ri", "limit": 3}, headers=KEY).json()["items"]) == 3


@pytest.mark.parametrize("q", ["x" * 61, "a b c d e", "123", "vado!"])
def test_invalid_query(client, q):
    r = client.get("/v2/conjugate", params={"q": q}, headers=KEY)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_query"


@pytest.mark.parametrize("route", ["/v2/conjugate?q=vado", "/v2/suggest?q=and"])
def test_api_key_is_required(client, route):
    assert client.get(route).status_code == 401
    assert client.get(route, headers={"X-API-Key": "wrong"}).status_code == 401


def test_v1_is_unchanged(client):
    body = client.get("/conjugate", params={"v": "vado"}, headers=KEY).json()
    assert body["success"] and body["data"]["queried"] == "andare"
    assert body["data"]["conjugations"]["tempi composti"]["passato prossimo"]["io"] == "sono andato"
