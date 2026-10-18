"""Státní svátky a pracovní dny ČR.

Pevné svátky + velikonočně závislé (Maškopust, Velký pátek, Velikonoční pondělí).
Velikonoce pro roky 2026–2028 (Anno Domini výpočet).
"""
from datetime import date, timedelta


# Velikonoce podle computus (Anno Domini formula).
# Funkční pro roky cca 1900–2099.
def _easter_sunday(year: int) -> date:
    """Vrátí datum Velikonoční neděle daného roku."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# Pevné státní svátky ČR (měsíc, den)
_FIXED_HOLIDAYS = [
    (1, 1),   # Obnovení samostatného českého státu
    (5, 1),   # Den práce
    (5, 8),   # Den vítězství
    (7, 5),   # Sv. Cyril a Metoděj
    (7, 6),   # Jan Hus
    (9, 28),  # Den české státnosti
    (10, 28), # Den nezávislosti
    (11, 17), # Den boje za svobodu a demokracii
    (12, 24), # Štědrý den
    (12, 25), # 1. svátek vánoční
    (12, 26), # 2. svátek vánoční
]


def _fixed_holidays(year: int) -> set[date]:
    return {date(year, m, d) for m, d in _FIXED_HOLIDAYS}


# Velikonočně závislé svátky — offset od velikonoční neděle
_EASTER_OFFSETS = {
    -47,   # Maškopust = Velikonoce − 47 dní
    -2,    # Velký pátek = Velikonoce − 2 dní
    1,     # Velikonoční pondělí = Velikonoce + 1
}


def _easter_holidays(year: int) -> set[date]:
    """Vrátí velikonoční svátky pro daný rok."""
    easter = _easter_sunday(year)
    return {easter + timedelta(days=offset) for offset in _EASTER_OFFSETS}


def _all_holidays(year: int) -> set[date]:
    """Všechny státní svátky pro daný rok."""
    return _fixed_holidays(year) | _easter_holidays(year)


def is_cz_workday(d: date) -> bool:
    """Je daný den pracovní den v ČR?

    Pracovní den = Po–Pá a není státní svátek.
    """
    if d.weekday() >= 5:  # So, Ne
        return False
    if d in _all_holidays(d.year):
        return False
    return True


def holidays_between(start: date, end: date) -> list[date]:
    """Všechny státní svátky v rozmezí [start, end] (včetně hranic)."""
    result = []
    year = start.year
    while year <= end.year:
        for h in _all_holidays(year):
            if start <= h <= end:
                result.append(h)
        year += 1
    result.sort()
    return result
