/** Datový model `changelog.json` — generuje se z `.git` při buildu web image
 * (frontend-web/scripts/gen-changelog.mjs); commítnutý stub v `public/` slouží
 * pro host dev. Viz stránka /changelog a /o-programu. */

export interface ChangelogEntry {
  sha: string;
  /** datum commitu (RRRR-MM-DD) */
  date: string;
  /** conventional commit typ (feat, fix, ...) nebo "other" */
  type: string;
  scope: string;
  subject: string;
}

export interface ChangelogBuild {
  sha: string;
  /** čas buildu UTC */
  date: string;
  /** "dev" | "prod" (build arg VITE_APP_LABEL) */
  label: string;
}

export interface ChangelogData {
  build: ChangelogBuild | null;
  entries: ChangelogEntry[];
}

export type CategoryKey =
  | "feat"
  | "fix"
  | "refactor"
  | "docs"
  | "infra"
  | "test"
  | "other";

/** Kategorie v pořadí, v jakém se zobrazí na /changelog. */
export const CATEGORIES: { key: CategoryKey; label: string }[] = [
  { key: "feat", label: "Nové funkce" },
  { key: "fix", label: "Opravy chyb" },
  { key: "refactor", label: "Změny a úpravy" },
  { key: "docs", label: "Dokumentace" },
  { key: "infra", label: "Infrastruktura" },
  { key: "test", label: "Testy" },
  { key: "other", label: "Ostatní" },
];

/** Commit typ → kategorie (neznámé typy spadnou do Ostatní). */
export function categoryOf(type: string): CategoryKey {
  switch (type.toLowerCase()) {
    case "feat":
      return "feat";
    case "fix":
      return "fix";
    case "refactor":
    case "perf":
      return "refactor";
    case "docs":
      return "docs";
    case "infra":
    case "build":
    case "ci":
      return "infra";
    case "test":
      return "test";
    default:
      return "other";
  }
}

export interface CategoryGroup {
  key: CategoryKey;
  label: string;
  items: ChangelogEntry[];
}

/** Seskupí entry podle kategorie; prázdné kategorie vypadnou, pořadí = CATEGORIES. */
export function groupByCategory(entries: ChangelogEntry[]): CategoryGroup[] {
  const byKey = new Map<CategoryKey, ChangelogEntry[]>();
  for (const entry of entries) {
    const key = categoryOf(entry.type);
    const list = byKey.get(key) ?? [];
    list.push(entry);
    byKey.set(key, list);
  }
  return CATEGORIES.filter((c) => byKey.has(c.key)).map((c) => ({
    key: c.key,
    label: c.label,
    items: byKey.get(c.key)!,
  }));
}
