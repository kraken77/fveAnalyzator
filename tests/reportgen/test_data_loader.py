"""Data loader: čisté API bez debug výstupu na stdout.

`load_consumption_data` se volá z workflowu produkčního backendu — nesmí
tisknout do stdout (kontaminuje logy uvicornu).
"""
import pandas as pd

from app.data_loader import load_consumption_data


def test_load_consumption_data_ne_tiskne_debug_printy(capsys):
    df = load_consumption_data(target_annual_kwh=10_000)

    out = capsys.readouterr().out
    assert "DEBUG" not in out
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "consumption_kWh" in df.columns
    assert df["consumption_kWh"].sum() > 0
