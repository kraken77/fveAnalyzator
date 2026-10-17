import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// `appEnv` čte build-time hodnotu (import.meta.env) — v testu ho mockujeme
// změnitelným stavem, abychom otestovali obě instance.
const { state } = vi.hoisted(() => ({ state: { label: "dev" as string } }));
vi.mock("../lib/appEnv", () => ({
  get APP_LABEL() {
    return state.label;
  },
}));

import DevBanner from "./DevBanner";

describe("DevBanner", () => {
  it("dev instance: zobrazí oranžový pas s textem", () => {
    state.label = "dev";
    render(<DevBanner />);
    const banner = screen.getByTestId("dev-banner");
    expect(banner).toBeTruthy();
    expect(banner.textContent).toMatch(/vývojová verze/i);
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
