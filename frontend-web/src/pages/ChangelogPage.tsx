import { groupByCategory } from "../lib/changelog";
import { useChangelog } from "../lib/useChangelog";

/** Veřejný přehled commitů v aktuálně nasazené verzi — dev i prod image
 * si generují vlastní changelog.json při buildu (viz scripts/gen-changelog.mjs). */
export default function ChangelogPage() {
  const { data, error } = useChangelog();

  if (error) {
    return <p className="text-sm text-slate-500">Changelog se nepodařilo načíst.</p>;
  }
  if (!data) {
    return null; // načítání
  }
  if (!data.build || data.entries.length === 0) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold mb-4">Changelog</h1>
        <p className="text-sm text-slate-500">
          Changelog se generuje při buildu Docker image — tento bundle neobsahuje historii commitů.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl" data-testid="changelog-page">
      <h1 className="text-2xl font-bold mb-4">Changelog</h1>
      <div className="rounded-lg border border-slate-200 bg-white p-4 mb-6">
        <p className="text-[10px] uppercase font-bold tracking-wide text-slateMuted mb-1">
          Aktuální build
        </p>
        <p className="text-sm font-semibold">
          <span data-testid="changelog-build-label">
            {data.build.label === "dev" ? "Dev instance" : "Produkce"}
          </span>{" "}
          · <span data-testid="changelog-build-sha">{data.build.sha}</span> ·{" "}
          <span data-testid="changelog-build-date">{data.build.date}</span>
        </p>
      </div>
      {groupByCategory(data.entries).map((cat) => (
        <section key={cat.key} className="mb-5">
          <h2 className="text-xs font-bold uppercase tracking-wide text-navy border-b border-slate-200 pb-1 mb-2">
            {cat.label}
          </h2>
          <ul className="space-y-1.5">
            {cat.items.map((entry) => (
              <li
                key={`${entry.sha}-${entry.subject}`}
                className="flex items-baseline gap-3 rounded border border-slate-100 bg-white px-3 py-2 text-sm"
              >
                <span className="shrink-0 text-xs text-slate-400">{entry.date}</span>
                <span className="flex-1">
                  {entry.subject}
                  {entry.scope && (
                    <span className="ml-1 text-xs text-slate-400">[{entry.scope}]</span>
                  )}
                </span>
                <code className="shrink-0 text-[10px] text-slate-400">{entry.sha}</code>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
