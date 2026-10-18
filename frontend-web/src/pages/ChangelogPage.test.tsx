import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChangelogPage from "./ChangelogPage";

const sample = {
  build: { sha: "8218a80", date: "2026-10-18 09:23 UTC", label: "dev" },
  entries: [
    { sha: "9c3e2f1", date: "2026-10-18", type: "feat", scope: "web", subject: "git sha + cas buildu do oranzoveho pasu" },
    { sha: "a1b2c3d", date: "2026-10-17", type: "fix", scope: "dispecink", subject: "oprava tooltipu" },
  ],
};

function mockFetch(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })),
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe("ChangelogPage", () => {
  it("zobrazi build kartu a sekce dle typu commitu", async () => {
    mockFetch(sample);
    render(<ChangelogPage />);

    expect(await screen.findByText("8218a80")).toBeTruthy();
    expect(screen.getByText("Dev instance")).toBeTruthy();
    expect(screen.getByText("2026-10-18 09:23 UTC")).toBeTruthy();
    expect(screen.getByText("Nové funkce")).toBeTruthy();
    expect(screen.getByText("Opravy chyb")).toBeTruthy();
    expect(screen.getByText("git sha + cas buildu do oranzoveho pasu")).toBeTruthy();
    expect(screen.getByText("oprava tooltipu")).toBeTruthy();
    expect(screen.getByText("[web]")).toBeTruthy();
  });

  it("stub (prazdny build) zobrazi informaci o generovani pri buildu", async () => {
    mockFetch({ build: null, entries: [] });
    render(<ChangelogPage />);
    expect(await screen.findByText(/generuje při buildu/i)).toBeTruthy();
  });
});
