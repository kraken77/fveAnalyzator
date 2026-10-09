"""Shoda výchozích parametrů FVE mezi frontendem a backendem.

`DEFAULT_FVE_PARAMS` (frontend) se parsuje z TypeScriptu, aby se drift
projevil jako padající test — ne až tím, že formulář pošle jiné defaulty
než výpočet.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FVE_TS = REPO / "frontend-web" / "src" / "api" / "fve.ts"

from app.fve_analysis import _DEFAULTS  # noqa: E402
from reportgen.fve_router import FveParams  # noqa: E402


def _parse_ts_defaults(path: Path) -> dict:
    """Přečte `DEFAULT_FVE_PARAMS` z `.ts` jako dict.

    Záměrně hloupý řádkový parser (žádný TS parser): hodnoty jsou jednořádkové.
    Pole a objekty se přeskočí (řeší je až porovnání společných klíčů).
    """
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"DEFAULT_FVE_PARAMS\s*:\s*FveParams\s*=\s*\{(.*?)\n\};", text, re.S)
    assert match, "DEFAULT_FVE_PARAMS nenalezen v fve.ts"
    out: dict = {}
    for raw in match.group(1).splitlines():
        line = raw.split("//")[0].strip().rstrip(",")
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") or value.startswith("{"):
            continue
        if value in ("null", "None"):
            out[key] = None
        elif value == "true":
            out[key] = True
        elif value == "false":
            out[key] = False
        elif value[:1] in ('"', "'"):
            out[key] = value[1:-1]
        else:
            out[key] = float(value)
    return out


def test_defaults_match_across_frontend_and_backend():
    """Společné skalární klíče musí mít ve všech třech zdrojích stejnou hodnotu."""
    ts = _parse_ts_defaults(FVE_TS)
    fields = FveParams.model_fields
    common = [
        k for k in ts
        if k in _DEFAULTS and k in fields and "appliance" not in k
    ]
    assert common, "parser nenačetl žádné klíče — zkontroluj vzor v fve.ts"
    for key in common:
        assert ts[key] == _DEFAULTS[key], (
            f"{key}: .ts={ts[key]!r} != _DEFAULTS={_DEFAULTS[key]!r}")
        assert ts[key] == fields[key].default, (
            f"{key}: .ts={ts[key]!r} != FveParams={fields[key].default!r}")


def test_default_gps_is_usti_nad_labem():
    """Defaultní GPS je Ústí — jinak analýza počítá pro Prahu."""
    ts = _parse_ts_defaults(FVE_TS)
    for source in (_DEFAULTS, ts):
        assert (source["latitude"], source["longitude"]) == (50.6607, 14.03227)
    assert FveParams.model_fields["latitude"].default == 50.6607
    assert FveParams.model_fields["longitude"].default == 14.03227
