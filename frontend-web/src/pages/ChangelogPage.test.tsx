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
    // kategorie se objeví dvakrát (sticky TOC + nadpis karty)
    expect(screen.getAllByText("Nové funkce").length).toBe(2);
    expect(screen.getAllByText("Opravy chyb").length).toBe(2);
    expect(screen.getByText("git sha + cas buildu do oranzoveho pasu")).toBeTruthy();
    expect(screen.getByText("oprava tooltipu")).toBeTruthy();
    expect(screen.getByText("[web]")).toBeTruthy();
  });

   it("sticky nav: odkaz na kazdou neprazdou kategorii + id na kartach", async () => {
    mockFetch(sample);
    const { container } = render(<ChangelogPage />);
    await screen.findByText("8218a80");

    const nav = container.querySelector('[data-testid="changelog-toc"]');
    expect(nav).toBeTruthy();
    const links = nav!.querySelectorAll("a");
    expect(links.length).toBe(2); // ve sample jen feat + fix
    expect(links[0].getAttribute("href")).toBe("#feat");
    expect(links[0].textContent).toBe("Nové funkce");
    expect(links[1].getAttribute("href")).toBe("#fix");
    expect(links[1].textContent).toBe("Opravy chyb");

    // karta ma odpovidajici id pro kotvu
    expect(container.querySelector('section[id="feat"]')).toBeTruthy();
    expect(container.querySelector('section[id="fix"]')).toBeTruthy();
  });

  it("stub (prazdny build) zobrazi informaci o generovani pri buildu", async () => {
    mockFetch({ build: null, entries: [] });
    render(<ChangelogPage />);
    expect(await screen.findByText(/generuje při buildu/i)).toBeTruthy();
  });
});
