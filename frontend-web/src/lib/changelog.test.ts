import { describe, expect, it } from "vitest";
import { categoryOf, groupByCategory, type ChangelogEntry } from "./changelog";

const e = (type: string, subject: string, sha = "abc1234"): ChangelogEntry => ({
  sha,
  date: "2026-10-18",
  type,
  scope: "",
  subject,
});

describe("categoryOf", () => {
  it("mapuje conventional typy na kategorie", () => {
    expect(categoryOf("feat")).toBe("feat");
    expect(categoryOf("fix")).toBe("fix");
    expect(categoryOf("docs")).toBe("docs");
    expect(categoryOf("infra")).toBe("infra");
    expect(categoryOf("test")).toBe("test");
  });

  it("refactor a perf spadnou do 'Změny a úpravy'", () => {
    expect(categoryOf("refactor")).toBe("refactor");
    expect(categoryOf("perf")).toBe("refactor");
  });

  it("build/ci spadnou do infrastrukture, neznámé do Ostatní", () => {
    expect(categoryOf("build")).toBe("infra");
    expect(categoryOf("ci")).toBe("infra");
    expect(categoryOf("chore")).toBe("other");
    expect(categoryOf("updater")).toBe("other");
    expect(categoryOf("")).toBe("other");
  });
});

describe("groupByCategory", () => {
  it("seskupí položky a drží pořadí kategorií z CATEGORIES", () => {
    const groups = groupByCategory([
      e("test", "testy", "t1"),
      e("fix", "oprava", "f1"),
      e("feat", "funkce", "a1"),
      e("feat", "funkce 2", "a2"),
      e("docs", "docs", "d1"),
    ]);
    expect(groups.map((g) => g.key)).toEqual(["feat", "fix", "docs", "test"]);
    expect(groups[0].label).toBe("Nové funkce");
    expect(groups[0].items.map((i) => i.sha)).toEqual(["a1", "a2"]);
  });

  it("vynechá prázdné kategorie a prázdný vstup vrací []", () => {
    expect(groupByCategory([e("fix", "oprama")]).map((g) => g.key)).toEqual(["fix"]);
    expect(groupByCategory([])).toEqual([]);
  });
});
