import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AboutPage from "./AboutPage";

const sample = {
  build: { sha: "8218a80", date: "2026-10-18 09:23 UTC", label: "prod" },
  entries: [],
};

function mockFetch(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })),
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe("AboutPage", () => {
  it("zobrazi popis, build kartu a odkaz na changelog", async () => {
    mockFetch(sample);
    render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/FVE analýz/i)).toBeTruthy();
    expect(screen.getByText("Produkce")).toBeTruthy();
    expect(screen.getByText("8218a80")).toBeTruthy();
    const link = screen.getByTestId("about-changelog-link");
    expect(link.getAttribute("href")).toBe("/changelog");
  });
});
