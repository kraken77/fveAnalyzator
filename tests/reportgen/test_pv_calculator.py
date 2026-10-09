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
