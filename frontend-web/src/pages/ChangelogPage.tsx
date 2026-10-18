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
      {/* Sticky hlavička: název + build karta + TOC — přichycená pod app
          headerem (h-16), ať uživatel vždy ví, kde je a kam skákat. */}
      <div
        className="sticky top-16 z-30 mb-4 bg-[#f8fafc]/95 py-2 backdrop-blur"
        data-testid="changelog-sticky"
      >
      {/* Název + kompaktní build karta vedle sebe (na mobile se přelomí). */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-2xl font-bold">Changelog</h1>
        <div
          className="rounded-lg border border-slate-200 bg-white px-4 py-2.5"
          data-testid="changelog-build"
        >
          <p className="text-[10px] uppercase font-bold tracking-wide text-slateMuted">
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
      </div>
      {/* Panel odkazů na karty (sticky je celý wrapper nahoře). */}
      <nav
        className="mt-2 rounded-lg border border-slate-200 bg-white/95 backdrop-blur"
        data-testid="changelog-toc"
      >
        <div className="flex gap-1 overflow-x-auto whitespace-nowrap px-3 py-1.5">
          {groupByCategory(data.entries).map((cat) => (
            <a
              key={cat.key}
              href={`#${cat.key}`}
              className="rounded px-2.5 py-1 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-navy"
            >
              {cat.label}
            </a>
          ))}
        </div>
      </nav>
      </div>
      {/* Každá kategorie = samostatná karta (nadpis uvnitř, položky jako řádky);
          id + scroll-mt pro kotvy (offset pod header + sticky hlavičku). */}
      {groupByCategory(data.entries).map((cat) => (
        <section
          key={cat.key}
          id={cat.key}
          className="mb-4 scroll-mt-44 rounded-lg border border-slate-200 bg-white p-4"
        >
          <h2 className="mb-3 text-xs font-bold uppercase tracking-wide text-navy">
            {cat.label}
          </h2>
          <ul className="divide-y divide-slate-100">
            {cat.items.map((entry) => (
              <li
                key={`${entry.sha}-${entry.subject}`}
                className="flex items-baseline gap-3 py-2 text-sm first:pt-0 last:pb-0"
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
