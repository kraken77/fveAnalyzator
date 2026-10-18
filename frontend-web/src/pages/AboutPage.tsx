import { Link } from "react-router-dom";
import { useChangelog } from "../lib/useChangelog";

/** Stránka „O programu“ — krátký popis + karta aktuální verze + odkaz na changelog. */
export default function AboutPage() {
  const { data, error } = useChangelog();
  const build = data?.build ?? null;

  return (
    <div className="max-w-2xl" data-testid="about-page">
      <h1 className="text-2xl font-bold mb-4">O programu</h1>
      <div className="rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed">
        <p className="mb-3">
          Interní nástroj <strong>Antelon Energy</strong> pro FVE analýzu a procesní
          pipeline zakázek (dispečink). Evidence projektů přes fáze od LEAD po Revizi,
          analýza výnosu fotovoltaických instalací (PVGIS) a sdílené odkazy s QR kódy
          pro zákazníky.
        </p>
        {build ? (
          <div className="border-t border-slate-100 pt-3">
            <p className="text-[10px] uppercase font-bold tracking-wide text-slateMuted mb-1">
              Tato verze
            </p>
            <p className="font-semibold">
              <span data-testid="about-build-label">
                {build.label === "dev" ? "Dev instance" : "Produkce"}
              </span>{" "}
              · <span data-testid="about-build-sha">{build.sha}</span> ·{" "}
              <span data-testid="about-build-date">{build.date}</span>
            </p>
            <Link
              to="/changelog"
              className="mt-2 inline-block font-semibold text-antelonGreen hover:underline"
              data-testid="about-changelog-link"
            >
              Changelog →
            </Link>
          </div>
        ) : (
          !error && <p className="text-slate-400">Verze se načítá…</p>
        )}
      </div>
    </div>
  );
}
