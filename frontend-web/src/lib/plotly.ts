/**
 * Plotly jen s typy grafů, které backend skutečně generuje.
 *
 * `plotly.js-dist-min` je plný bundle — 4,6 MB (1,4 MB gzip), protože obsahuje
 * všechny trace typy včetně 3D, map a WebGL. Vykreslujeme ale jen pět věcí,
 * takže se z toho naprostá většina nepoužije.
 *
 * Tenhle modul staví bundle z `plotly.js/lib/core` a registruje jen to
 * potřebné. `core` už obsahuje `scatter` (jediný trace, který se nedá
 * vyndat) — zbytek je potřeba zaregistrovat ručně.
 *
 * **Když backend začne generovat nový typ grafu, musí se sem přidat.**
 * Nechybí to nijak hlasitě: graf se prostě nevykreslí a do konzole spadne
 * chyba o neznámém trace typu. Hlídá to test v `test_plotly_traces.py`.
 *
 * Přehled, co backend používá (`backend/app/visualizer.py`):
 *   - `go.Scatter`   → core (nedá se vyndat)
 *   - `go.Bar`       → bar
 *   - `go.Pie`       → pie
 *   - `go.Sunburst`  → sunburst
 *   - `px.treemap`   → treemap
 *   - `calendars`    → `bar` s datovou osou (měsíční statistiky)
 */
import Plotly from "plotly.js/lib/core";
import bar from "plotly.js/lib/bar";
import pie from "plotly.js/lib/pie";
import treemap from "plotly.js/lib/treemap";
import sunburst from "plotly.js/lib/sunburst";
import calendars from "plotly.js/lib/calendars";

Plotly.register([bar, pie, treemap, sunburst, calendars]);

export default Plotly;
