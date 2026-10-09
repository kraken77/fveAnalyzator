"""Produkce FVE: teplotní ztráta a optimum (body 4a/4b).

`get_pv_production` i `get_optimal_pv_production` umí dostat syntetické
počasí přes `weather_data`, takže testy nepotřebují síť ani cache.
"""
import pandas as pd

from pv_calculator import (
    apply_temperature_derate,
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
