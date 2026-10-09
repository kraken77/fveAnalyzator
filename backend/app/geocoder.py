"""Geokódování přes Nominatim (OpenStreetMap).

Nominatim umí adresy i obce a vrací více kandidátů; UI si z nich vybere.
Politika OSM vyžaduje vlastní `User-Agent`; mezipaměť šetří opakované
dotazy a tlačítko v UI je během hledání zamčené.
"""
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "antelon-energy/1.0"

_CACHE: dict[str, list[dict]] = {}


def search(address: str, limit: int = 6) -> list[dict]:
    """Vrátí kandidáty z Nominatim. Prázdný vstup i nenalezeno → []."""
    address = (address or "").strip()
    if not address:
        return []

    key = f"{address.lower()}|{limit}"
    if key in _CACHE:
        return _CACHE[key]

    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": address,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
        },
        headers={"User-Agent": USER_AGENT, "Accept-Language": "cs"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json() or []

    results = [
        {
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "display_name": item.get("display_name", ""),
        }
        for item in data
    ]
    _CACHE[key] = results
    return results
