"""Ceník materiálů — jediné místo, kde se počítají počty kusů a investice
a kde se zapisuje cena.

`derive_qty` je čistá funkce (žádná DB). `set_material_price` je jediný
povolený zápis do `materials.price` a `material_prices`. Frontend má
vlastní zrcadlo `deriveQty` pro okamžitý součet — hodnoty se musí rovnat,
jinak se snímek a živý součet rozjedou; rozdíl hlídá Task 10.
"""
import math


def derive_qty(category: str, rating: float | None, params: dict) -> float:
    """Počet kusů dané komponenty pro definovaný výkon elektrárny.

    - panel:      ceil(kWp × 1000 / Wp)
    - inverter:   ceil(kWp / kW)
    - battery:    ceil(kapacita / kWh)
    - install, system, other: 1
    """
    kwp = float(params.get("kwp", 10.0))
    if category == "panel":
        if not rating:
            return 0.0
        return math.ceil(kwp * 1000 / rating)
    if category == "inverter":
        if not rating:
            return 0.0
        return math.ceil(kwp / rating)
    if category == "battery":
        kap = float(params.get("battery_capacity", 0.0))
        if not rating:
            return 0.0
        return math.ceil(kap / rating)
    return 1.0