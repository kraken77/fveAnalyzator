"""Produkce FVE: teplotní ztráta a optimum (body 4a/4b).

`get_pv_production` i `get_optimal_pv_production` umí dostat syntetické
počasí přes `weather_data`, takže testy nepotřebují síť ani cache.
"""
import pandas as pd

from pv_calculator import (
    apply_temperature_derate,
    fetch_pvgis_tmy_data,
    get_optimal_pv_production,
    get_pv_production,
)


def _weather(temp_air):
    """Tři polední hodiny — deterministické a bez nočních NaN."""
    times = pd.date_range("2024-06-21 10:00", periods=3, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "ghi": [800.0, 900.0, 850.0],
            "dni": [600.0, 700.0, 650.0],
            "dhi": [120.0, 130.0, 125.0],
            "temp_air": [temp_air, temp_air, temp_air],
            "wind_speed": [1.0, 1.0, 1.0],
        },
        index=times,
    )


def test_apply_temperature_derate_formula():
    """−0,4 %/°C nad 25 °C: při 45 °C je výkon 92 %."""
    assert apply_temperature_derate(1000.0, 25.0) == 1000.0
    assert apply_temperature_derate(1000.0, 45.0) == 920.0
    assert apply_temperature_derate(1000.0, 5.0) == 1080.0


def test_get_pv_production_applies_temperature_derate():
    """Vyšší teplota vzduchu musí snížit produkci — důkaz, že se derate volá."""
    _, cold = get_pv_production(
        50.0, 14.0, 35, 180, 10.0, weather_data=_weather(5.0))
    _, hot = get_pv_production(
        50.0, 14.0, 35, 180, 10.0, weather_data=_weather(45.0))
    assert hot < cold


def test_optimum_finds_best_tilt_and_never_exceeds_actual():
    """Optimum = maximum přes sklon 10–70° po 5°, azimut 180°.

    Sken zahrnuje i defaultní sklon 35°, takže optimum nikdy nesmí být
    menší než skutečná výroba pro tytéž podmínky → poměr ≤ 100 %.
    """
    weather = _weather(25.0)
    actual = get_pv_production(
        50.6607, 14.03227, 35, 180, 10.0,
        winter_loss_factor=10.0, weather_data=weather)[1]
    optimum = get_optimal_pv_production(
        50.6607, 14.03227, 10.0,
        winter_loss_factor=10.0, weather_data=weather)

    brute = max(
        get_pv_production(50.6607, 14.03227, tilt, 180, 10.0,
                          winter_loss_factor=10.0, weather_data=weather)[1]
        for tilt in range(10, 71, 5)
    )
    assert abs(optimum - brute) < 1e-9
    assert optimum >= actual - 1e-9


def test_optimum_accepts_winter_loss_factor():
    """Zimní ztráta se propouští, aby se reál a optimum lišily jen orientací.

    Počasí obsahuje leden i červenec; při 100% zimní ztrátě musí být
    prosinec/leden/únor nulový, takže optimum klesne.
    """
    times = (
        pd.date_range("2024-01-15 12:00", periods=3, freq="h", tz="UTC")
        .append(pd.date_range("2024-07-15 12:00", periods=3, freq="h", tz="UTC"))
    )
    weather = pd.DataFrame(
        {
            "ghi": [500.0] * 6, "dni": [400.0] * 6, "dhi": [100.0] * 6,
            "temp_air": [25.0] * 6, "wind_speed": [1.0] * 6,
        },
        index=times,
    )
    bez = get_optimal_pv_production(
        50.6607, 14.03227, 10.0, winter_loss_factor=None, weather_data=weather)
    se = get_optimal_pv_production(
        50.6607, 14.03227, 10.0, winter_loss_factor=100.0, weather_data=weather)
    assert se < bez


def test_optimum_never_below_actual_for_any_orientation():
    """Optimum ≥ reálná výroba pro JAKOUKOLIV orientaci (bod 4b, nález N1).

    Reálná orientace se přidá jako kandidát skenu, takže invariant drží i pro
    sklon mimo mřížku (37°), jiný azimut (135°/270°) a jižní polokouli.
    """
    weather = _weather(25.0)
    for lat, tilt, az in [
        (50.6607, 35, 180),
        (50.6607, 37, 135),
        (50.6607, 55, 270),
        (50.6607, 10, 90),
        (50.6607, 70, 0),
        (-33.87, 35, 0),
        (-33.87, 30, 359),
        (-33.87, 45, 180),
    ]:
        actual = get_pv_production(
            lat, 14.03227, tilt, az, 10.0,
            winter_loss_factor=10.0, weather_data=weather)[1]
        optimum = get_optimal_pv_production(
            lat, 14.03227, 10.0, winter_loss_factor=10.0, weather_data=weather,
            surface_tilt=tilt, surface_azimuth=az)
        assert optimum >= actual - 1e-9, (lat, tilt, az, actual, optimum)


def test_optimum_searches_southern_hemisphere_azimuth():
    """Na jižní polokouli musí optimum hledat na azimutu 0°, ne 180° (bod 4b).

    Voláno BEZ konkrétní orientace (žádný append kandidáta), takže optimum je
    čisté maximum mříže na optimálním azimutu hemisféry. Pro lat = −33,87°
    musí být ≥ výroba na reálném (35°, 0°); s natvrdo 180° by optimum spadlo
    pod ni a test by padl.
    """
    weather = _weather(25.0)
    actual_south = get_pv_production(
        -33.87, 14.03227, 35, 0, 10.0,
        winter_loss_factor=10.0, weather_data=weather)[1]
    optimum = get_optimal_pv_production(
        -33.87, 14.03227, 10.0,
        winter_loss_factor=10.0, weather_data=weather)
    assert optimum >= actual_south - 1e-9


def test_optimum_never_below_actual_for_off_grid_azimuth_real_tmy():
    """Reálná orientace (35°, 175°) mimo mříž 180° na skutečném TMY Ústí (I1).

    Na reálném TMY Ústí z cache `data/weather_cache.db` (stejná data, která
    čte `app.data_loader.load_production_data`) dává azimut 175° vyšší výrobu
    než nejlepší mřížový kandidát na 180°. Invariant optimum ≥ actual proto
    drží JEN díky tomu, že se reálná orientace přidá mezi kandidáty: bez
    `candidates.append(...)` je optimum = mříž na 180° < actual a test padne.
    Záměrně proto NEpředáváme syntetické počasí — diskriminuje jen reálná data.
    """
    from app.data_loader import load_production_data

    _, actual, optimum = load_production_data(
        kwp=10.0, latitude=50.6607, longitude=14.03227,
        surface_tilt=35, surface_azimuth=175,
    )

    # Premisa diskriminace: mříž na 180° je opravdu horší než reálných 175°.
    weather = fetch_pvgis_tmy_data(50.6607, 14.03227)
    assert weather is not None
    grid = get_optimal_pv_production(
        50.6607, 14.03227, 10.0,
        winter_loss_factor=10.0, weather_data=weather)
    assert grid < actual

    assert optimum >= actual - 1e-9
