"""Registr oddílů PDF reportu — jediný zdroj pravdy pro skládání dokumentu.

Kanonické pořadí `SECTIONS` je default. `resolve_sections` sanitizuje
požadavek klienta: ignoruje neznámé id, vždy přidá pevný základ a rám
(intro na začátek, slovník na konec) a zachová pořadí zbytku.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    description: str
    base: bool = False
    needs_economic: bool = False
    frame: str | None = None  # "first" | "last" | None


SECTIONS: tuple[Section, ...] = (
    Section("intro", "Jak číst tento report",
            "Úvod vysvětlující, co dokument obsahuje a jak ho číst.", frame="first"),
    Section("summary", "Souhrnné výsledky",
            "Hlavní čísla analýzy: roční úspora, vlastní spotřeba, export.", base=True),
    Section("input_params", "Vstupní parametry",
            "Přehled všech vstupů, ze kterých se počítalo."),
    Section("energy_balance", "Energetická bilance",
            "Roční tok energie a peněz mezi domácností a sítí."),
    Section("monthly_stats", "Měsíční statistika výroby a spotřeby",
            "Graf měsíční výroby a spotřeby."),
    Section("energy_charts", "Grafy (využití výroby a úspory)",
            "Kam se vyrobená energie a úspory rozdělily."),
    Section("monthly_summary", "Měsíční bilance",
            "Tabulka měsíčních toků energie a úspor."),
    Section("recommendations", "Doporučené strategie a scénáře",
            "Doporučení pro provoz a nastavení."),
    Section("economic_metrics", "Ekonomická analýza",
            "Návratnost, NPV a výnosy investice.", base=True, needs_economic=True),
    Section("investment_chart", "Investice vs S&P500",
            "Srovnání výnosu FVE a pasivního investování.", needs_economic=True),
    Section("investment_composition", "Složení investice",
            "Z čeho se investice skládá a kolik stojí.", base=True, needs_economic=True),
    Section("appendix_a", "Příloha A — Detail spotřebičů (ročně)",
            "Roční bilance po jednotlivých spotřebičích."),
    Section("appendix_b", "Příloha B — Měsíční bilance spotřebičů (kWh)",
            "Měsíční bilance po spotřebičích."),
    Section("appendix_c", "Příloha C — Detail nastavení spotřebičů",
            "Jak jsou spotřebiče nastavené."),
    Section("appendix_d", "Příloha D — Ekonomický plán po jednotlivých letech",
            "Roční ekonomický plán investice.", needs_economic=True),
    Section("glossary", "Slovníček pojmů",
            "Vysvětlení použitých pojmů.", frame="last"),
)

_BY_ID = {s.id: s for s in SECTIONS}
BASE_IDS: tuple[str, ...] = tuple(s.id for s in SECTIONS if s.base)
FRAME_FIRST: tuple[str, ...] = tuple(s.id for s in SECTIONS if s.frame == "first")
FRAME_LAST: tuple[str, ...] = tuple(s.id for s in SECTIONS if s.frame == "last")
ALL_IDS: tuple[str, ...] = tuple(s.id for s in SECTIONS)


def resolve_sections(requested: list[str] | None, *, has_economic: bool = True) -> list[str]:
    """Vrátí seřazený seznam id k vykreslení (sanitizovaný).

    - `None` → kanonické pořadí všech oddílů.
    - Neznámé id se ignorují.
    - Pevný základ a rám se vždy doplní (intro první, slovník poslední).
    - Oddíly vyžadující ekonomiku se vynechají, když `has_economic=False`.
    """
    if requested is None:
        ids = list(ALL_IDS)
    else:
        ids = [i for i in requested if i in _BY_ID]
        for s in SECTIONS:  # doplň chybějící pevný základ (kanonické pořadí)
            if s.base and s.id not in ids:
                ids.append(s.id)

    if not has_economic:
        ids = [i for i in ids if not _BY_ID[i].needs_economic]

    # rám: first přesunout na začátek, last na konec
    ids = [i for i in ids if _BY_ID[i].frame != "first"]
    ids = [i for i in ids if _BY_ID[i].frame != "last"]
    ids = list(FRAME_FIRST) + ids + list(FRAME_LAST)

    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def sections_metadata() -> list[dict]:
    """Metadata oddílů pro frontend (modální výběr) v kanonickém pořadí."""
    return [
        {"id": s.id, "label": s.label, "description": s.description, "base": s.base}
        for s in SECTIONS
    ]
