"""Frontend ořezává Plotly na jen použité typy grafů.

`frontend-web/src/lib/plotly.ts` staví partial bundle z `plotly.js/lib/core`
a registruje jen pár trace modulů. Plný bundle je 4,6 MB (1,4 MB gzip);
ořezaný je zlomek. Cena za to je tichý failure mód: když backend začne
generovat typ grafu, který není zaregistrovaný, **graf se prostě nevykreslí**
a chyba se objeví jen v konzoli prohlížeče. `tsc -b` ani `vite build` to
nechytí, protože v TypeScriptu je typ grafu jen string.

Tyto testy to hlídají ze strany backendu — čtou, co `visualizer.py` skutečně
vyrábí, a porovnávají to s tím, co frontend registruje.

Když test spadne, řešení je přidat modul do `Plotly.register([...])`
v `frontend-web/src/lib/plotly.ts`.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VISUALIZER = REPO / "backend" / "app" / "visualizer.py"
PLOTLY_TS = REPO / "frontend-web" / "src" / "lib" / "plotly.ts"

# graph_objects: `go.<Nazev>(` → typ trace
GO_TO_TRACE = {
    "Scatter": "scatter",
    "Scattergl": "scattergl",
    "Bar": "bar",
    "Pie": "pie",
    "Sunburst": "sunburst",
    "Treemap": "treemap",
    "Icicle": "icicle",
    "Funnelarea": "funnelarea",
    "Histogram": "histogram",
}

# plotly.express: `px.<nazev>(` → typ trace
PX_TO_TRACE = {
    "bar": "bar",
    "line": "scatter",
    "scatter": "scatter",
    "pie": "pie",
    "sunburst": "sunburst",
    "treemap": "treemap",
    "area": "scatter",
    "histogram": "histogram",
}

# `go.Figure` je kontejner, ne trace — v mapě být nesmí.
NOT_A_TRACE = {"Figure"}

# scatter registruje `plotly.js/lib/core` sám a nedá se vyndat
# (viz node_modules/plotly.js/src/core.js: "scatter is the only trace
# included by default").
ALWAYS_REGISTERED = {"scatter"}


def _go_trace_names() -> set:
    src = VISUALIZER.read_text(encoding="utf-8")
    found = set(re.findall(r"\bgo\.([A-Z]\w*)\s*\(", src))
    return found - NOT_A_TRACE


def _px_trace_names() -> set:
    src = VISUALIZER.read_text(encoding="utf-8")
    return set(re.findall(r"\bpx\.([a-z_]\w*)\s*\(", src))


def _needed_traces() -> set:
    return ({GO_TO_TRACE[n] for n in _go_trace_names() if n in GO_TO_TRACE}
            | {PX_TO_TRACE[n] for n in _px_trace_names() if n in PX_TO_TRACE})


def _registered_modules() -> set:
    """Jména modulů v `Plotly.register([...])` — importy z plotly.js/lib/*."""
    src = PLOTLY_TS.read_text(encoding="utf-8")
    match = re.search(r"Plotly\.register\(\[(.*?)\]\)", src, re.S)
    assert match, "v plotly.ts není žádné Plotly.register([...])"
    return set(re.findall(r"\b([a-z_]\w*)\b", match.group(1)))


def test_frontend_registers_every_trace_the_backend_uses():
    """Každý typ grafu, který backend vyrobí, musí být ve frontendu zaregistrovaný.

    `scatter` se odečítá — ten registruje `plotly.js/lib/core` sám a nedá se
    vyndat, takže ho frontend registrovat nemá (hlídá to samostatný test níže).
    """
    missing = _needed_traces() - _registered_modules() - ALWAYS_REGISTERED
    assert not missing, (
        f"Backend generuje {sorted(missing)}, ale frontend je nemá v "
        f"Plotly.register([...]) v {PLOTLY_TS.relative_to(REPO)} — "
        f"takto vyrobený graf se v prohlížeči nevykreslí."
    )


def test_every_backend_go_call_has_a_known_trace_mapping():
    """Pojistka proti slepé skvrně mapy.

    Kdyby někdo do `visualizer.py` přidal `go.Violin(...)` a v mapě výše
    chyběl, `test_frontend_registers_every_trace...` by prošel (neznámý
    název se tiše ignoruje), ale graf by se nevykreslil. Tento test
    selže dřív, protože hlásí neznámý konstruktor.
    """
    unknown = sorted(n for n in _go_trace_names() if n not in GO_TO_TRACE)
    assert not unknown, (
        f"visualizer.py používá go.{unknown}, což není v GO_TO_TRACE. "
        f"Doplň mapování a pak i registraci ve frontendu."
    )


def test_every_backend_px_call_has_a_known_trace_mapping():
    """Totéž pro plotly.express."""
    unknown = sorted(n for n in _px_trace_names() if n not in PX_TO_TRACE)
    assert not unknown, (
        f"visualizer.py používá px.{unknown}, což není v PX_TO_TRACE. "
        f"Doplň mapování a pak i registraci ve frontendu."
    )


def test_core_traces_are_not_registered_redundantly():
    """`scatter` je v core vždy — kdyby ho frontend registroval, plýtvá to.

    Není to chyba, ale je to signál, že někdo nepochopil, co core dělá.
    """
    assert not (_registered_modules() & ALWAYS_REGISTERED), (
        "plotly.ts registruje 'scatter', ale ten už je v plotly.js/lib/core. "
        "Zbytek registrace je omyl — vyhoď ho."
    )
