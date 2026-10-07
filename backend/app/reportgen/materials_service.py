"""Ceník materiálů — jediné místo, kde se počítají počty kusů a investice
a kde se zapisuje cena.

`derive_qty` je čistá funkce (žádná DB). `set_material_price` je jediný
povolený zápis do `materials.price` a `material_prices`. Frontend má
vlastní zrcadlo `deriveQty` pro okamžitý součet — hodnoty se musí rovnat,
jinak se snímek a živý součet rozjedou; rozdíl hlídá Task 10.
"""
import math
from datetime import date, timedelta

from .storage import Material, MaterialPrice


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


def set_material_price(db, material_id: int, price: float, valid_from: date,
                       created_by: int | None = None) -> MaterialPrice:
    """Zapíše novou cenu a uzavře předchozí otevřený řádek.

    Jediné povolené místo zápisu do `material_prices` i `materials.price`.
    Necommituje — transakci uzavírá volající.
    """
    prev = (db.query(MaterialPrice)
            .filter(MaterialPrice.material_id == material_id,
                    MaterialPrice.valid_to.is_(None))
            .order_by(MaterialPrice.valid_from.desc())
            .first())
    if prev is not None:
        prev.valid_to = valid_from - timedelta(days=1)

    row = MaterialPrice(material_id=material_id, price=price,
                        valid_from=valid_from, valid_to=None,
                        created_by=created_by)
    db.add(row)

    mat = db.query(Material).filter(Material.id == material_id).first()
    if mat is not None:
        mat.price = price
    db.flush()
    return row


def current_price(db, material_id: int, on: date) -> float | None:
    """Nejnovější cena platná k dni `on`, nebo None když žádná neplatí."""
    row = (db.query(MaterialPrice)
           .filter(MaterialPrice.material_id == material_id,
                   MaterialPrice.valid_from <= on,
                   (MaterialPrice.valid_to.is_(None))
                   | (MaterialPrice.valid_to >= on))
           .order_by(MaterialPrice.valid_from.desc())
           .first())
    return row.price if row is not None else None