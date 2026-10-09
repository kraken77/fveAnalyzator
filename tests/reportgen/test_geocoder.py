"""Geocoder Nominatim — unit testy s mocknutým `requests.get`.

Živé testy zůstávají v test_fve_api.py; tady ověřujeme kontrakt a hlavičky
bez sítě (User-Agent je povinný podle politiky OSM).
"""
import requests
import pytest

from app import geocoder


@pytest.fixture(autouse=True)
def _clear_geocoder_cache():
    """Izolace testů: `_CACHE` je modul-level a přežívá mezi testy.

    Bez úklidu by pořadí mohlo nechat `telnice|6` z mock testu a živý API
    test v test_fve_api.py by prošel z mocku, ne ze sítě.
    """
    geocoder._CACHE.clear()
    yield
    geocoder._CACHE.clear()


def _fake_response(payload):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    return _Resp()


def test_search_parses_results_and_sends_headers(monkeypatch):
    geocoder._CACHE.clear()
    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _fake_response([
            {"lat": "50.6812", "lon": "13.9876",
             "display_name": "Telnice, okres Ústí nad Labem, Česko"},
            {"lat": "49.1234", "lon": "16.5678",
             "display_name": "Telnice, okres Brno-venkov, Česko"},
        ])

    monkeypatch.setattr(requests, "get", fake_get)
    results = geocoder.search("Telnice")

    assert captured["url"] == "https://nominatim.openstreetmap.org/search"
    assert captured["params"]["q"] == "Telnice"
    assert captured["params"]["format"] == "jsonv2"
    assert captured["params"]["limit"] == 6
    assert captured["params"]["addressdetails"] == 1
    assert captured["headers"]["User-Agent"] == "antelon-energy/1.0"
    assert captured["headers"]["Accept-Language"] == "cs"
    assert captured["timeout"] == 10
    assert len(results) == 2
    assert results[0] == {
        "lat": 50.6812,
        "lon": 13.9876,
        "display_name": "Telnice, okres Ústí nad Labem, Česko",
    }


def test_search_is_cached(monkeypatch):
    geocoder._CACHE.clear()
    calls: list = []

    def fake_get(url, **kwargs):
        calls.append(1)
        return _fake_response(
            [{"lat": "1.0", "lon": "2.0", "display_name": "X"}])

    monkeypatch.setattr(requests, "get", fake_get)
    geocoder.search("Cache test")
    geocoder.search("Cache test")
    assert len(calls) == 1


def test_search_empty_input_does_not_hit_network(monkeypatch):
    geocoder._CACHE.clear()

    def fake_get(*args, **kwargs):
        raise AssertionError("prázdný vstup nesmí volat síť")

    monkeypatch.setattr(requests, "get", fake_get)
    assert geocoder.search("   ") == []
