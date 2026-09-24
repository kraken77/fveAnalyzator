"""Dotace NZÚ 2026 — oblast C.3 (FVE + baterie).

Port pravidel z nz2026-calculator/index.html (config řádky 545-546, výpočet
řádky 743-787):

- RD / dílčí opatření: perKwp 25 000 Kč, perKwh 15 000 Kč, max 400 000 Kč.
- BD / komplexní opatření: base 35 000 Kč pro prvních 5 kWp, extraKwp 40 000 Kč
  za každý další kWp, perKwh 15 000 Kč, kwhRatio 2 (min. poměr baterie:FVE).

Ruling: plán textově uváděl komplexní základ 25 000 Kč, ale index.html (zdroj,
na který plán odkazuje) má 35 000 Kč — řídím se kódem zdroje.
"""

# RD (dílčí)
RD = {"perKwp": 25000, "perKwh": 15000, "max": 400000}
# BD (komplexní)
BD = {"base": 35000, "baseKwp": 5, "extraKwp": 40000, "perKwh": 15000}


def compute_subsidy(kwp: float, battery_kwh: float, mode: str = "dilci") -> dict:
    """Vypočte dotaci C.3 pro instalovaný výkon FVE a kapacitu baterie.

    mode: 'dilci' (RD / dílčí opatření) | 'komplexni' (BD / komplexní).
    Vrací {castka, limit, sazby, podminky}.
    """
    kwp = max(0.0, float(kwp or 0))
    battery = max(0.0, float(battery_kwh or 0))

    if mode == "komplexni":
        cfg = BD
        if kwp <= cfg["baseKwp"]:
            pv = kwp * cfg["base"]
        else:
            pv = cfg["baseKwp"] * cfg["base"] + (kwp - cfg["baseKwp"]) * cfg["extraKwp"]
        limit = None
        brak = ["Komplexní opatření RD — zateplení povinné + využití OZE",
                "Minimální úvěr 100 000 Kč, max 2 000 000 Kč"]
    else:
        cfg = RD
        pv = kwp * cfg["perKwp"]
        limit = cfg["max"]
        brak = ["Instalovaný výkon FVE min. 3 kWp",
                "Max. dotace v oblasti C.3 400 000 Kč"]

    bat = battery * cfg["perKwh"]
    castka = pv + bat
    if limit:
        castka = min(castka, limit)

    return {
        "castka": round(castka, 2),
        "limit": limit,
        "sazby": {"pv_kw": kwp, "pv_castka": round(pv, 2),
                  "bat_kwh": battery, "bat_castka": round(bat, 2),
                  "per_kwp": cfg.get("perKwp") or cfg["base"],
                  "per_kwh": cfg["perKwh"]},
        "podminky": brak,
        "mode": mode,
    }