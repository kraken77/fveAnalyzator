import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { auth } = vi.hoisted(() => ({
  auth: {
    user: { id: 1, email: "admin@antelon.local", role: "admin", roles: ["admin"] },
    token: "tok",
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshMe: vi.fn(),
    roles: ["admin"],
    activeRole: "admin",
    setActiveRole: vi.fn(),
  },
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => auth,
  hasAnyRole: (_user: unknown, wanted: string[]) => wanted.includes("admin"),
}));
vi.mock("../api/client", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn(),
  },
}));

import Layout from "./Layout";

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout>
        <div>obsah</div>
      </Layout>
    </MemoryRouter>,
  );
}

describe("Layout — user menu", () => {
  it("dropdown obsahuje Changelog, O programu a Odhlásit", () => {
    renderLayout();
    fireEvent.click(screen.getByTestId("user-menu-btn"));

    expect(screen.getByTestId("user-menu-changelog").getAttribute("href")).toBe("/changelog");
    expect(screen.getByTestId("user-menu-about").getAttribute("href")).toBe("/o-programu");
    expect(screen.getByTestId("user-menu-logout")).toBeTruthy();
  });

  it("kliknutí na Odhlásit zavolá logout", () => {
    renderLayout();
    fireEvent.click(screen.getByTestId("user-menu-btn"));
    fireEvent.click(screen.getByTestId("user-menu-logout"));

    expect(auth.logout).toHaveBeenCalled();
  });
});
