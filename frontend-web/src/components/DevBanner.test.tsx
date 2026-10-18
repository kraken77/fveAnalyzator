import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// `appEnv` čte build-time hodnoty (import.meta.env) — v testu ho mockujeme
// změnitelným stavem, abychom otestovali obě instance.
const { state } = vi.hoisted(() => ({ state: { label: "dev" as string } }));
vi.mock("../lib/appEnv", () => ({
  get APP_LABEL() {
    return state.label;
  },
  get BUILD_SHA() {
    return "a1b2c3d";
  },
  get BUILD_DATE() {
    return "2026-10-18 23:05 UTC";
  },
}));

import DevBanner from "./DevBanner";

describe("DevBanner", () => {
  it("dev instance: zobrazí pas s textem, časem buildu a git SHA", () => {
    state.label = "dev";
    render(<DevBanner />);
    const banner = screen.getByTestId("dev-banner");
    expect(banner.textContent).toMatch(/vývojová verze/i);
    expect(banner.textContent).toContain("2026-10-18 23:05 UTC");
    expect(banner.textContent).toContain("a1b2c3d");
  });

  it("prod instance (i jiná hodnota): nic nevykreslí", () => {
    state.label = "prod";
    const { container } = render(<DevBanner />);
    expect(container.firstChild).toBeNull();

    state.label = "jiné";
    const { container: c2 } = render(<DevBanner />);
    expect(c2.firstElementChild).toBeNull();
  });
});
