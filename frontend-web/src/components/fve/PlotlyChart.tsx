import { useEffect, useRef } from "react";

// Naimportuje se dynamicky — plotly.js-dist-min je megabajt a načítat ho
// v hlavním bundlu by zdrželo první vykreslení celé aplikace.
let plotlyPromise: Promise<typeof import("plotly.js-dist-min")> | null = null;

function loadPlotly() {
  if (!plotlyPromise) {
    plotlyPromise = import("plotly.js-dist-min");
  }
  return plotlyPromise;
}

interface Props {
  /** JSON z backendu. plotly.io.to_json() vrací STRING, ne objekt. */
  json: string | null | undefined;
  height?: number;
  title?: string;
}

export default function PlotlyChart({ json, height = 380, title }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!json || !node) return;

    let cancelled = false;

    loadPlotly()
      .then((Plotly) => {
        if (cancelled || !ref.current) return;
        const figure = JSON.parse(json);
        // newPlot má overload na celou figuru — newPlot(node, {data, layout})
        Plotly.newPlot(node, figure);
        Plotly.relayout(node, { autosize: true, height });
      })
      .catch((err) => {
        console.error("PlotlyChart: vykreslení grafu selhalo", err);
      });

    return () => {
      cancelled = true;
      // purge je nutný — bez něj graf zůstane v DOM a leakne při unmountu
      if (node) loadPlotly().then((Plotly) => Plotly.purge(node));
    };
  }, [json, height]);

  if (!json) return null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      {title && <h4 className="font-semibold text-navy mb-2">{title}</h4>}
      <div ref={ref} style={{ height }} />
    </div>
  );
}
