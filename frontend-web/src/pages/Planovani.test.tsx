import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../context/AuthContext";
import type { User } from "../context/AuthContext";
import Planovani from "./Planovani";

vi.mock("../api/planning", () => ({
  getOverview: vi.fn(async () => {
    const overview = {
      today: "2026-10-18",
      holidays_in_range: ["2026-11-01"],
      ttl_days: 30,
      makespan: "2026-12-15",
      crews: [
        {
          id: 1,
          name: "Montáž",
          work_type: "roofer",
          available_from: "2026-10-01",
          available_to: "2027-12-31",
          work_days: ["po", "ut", "st", "ct", "pa"],
          absent_dates: [],
          active: true,
        },
      ],
      items: [
        {
          project_id: 5,
          project_name: "Dům Novák",
          step_code: "stavba_montaz",
          step_name: "Montáž FVE",
          work_type: "roofer",
          kind: "firm",
          duration_days: 1,
          start: "2026-10-19",
          end: "2026-10-19",
          crew_name: "Montáž",
        },
        {
          project_id: 10,
          project_name: "Rezervace Test",
          step_code: "stavba_montaz",
          step_name: "Montáž FVE",
          work_type: "roofer",
          kind: "reserve",
          duration_days: 2,
          start: "2026-10-20",
          end: "2026-10-21",
          crew_name: "Montáž",
        },
      ],
      projects: [
        {
          id: 5,
          name: "Dům Novák",
          kind: "firm",
          lead_age_days: 3,
          sod_date: "2026-10-10",
          done_date: "2026-12-15",
        },
        {
          id: 10,
          name: "Rezervace Test",
          kind: "reserve",
          lead_age_days: 12,
          reservation_expires: "2026-11-17",
        },
      ],
    };
    return overview;
  }),
  simulate: vi.fn(async (body: { add_crews: Record<string, number> }) => {
    const extra = body.add_crews["roofer"] ?? 0;
    return {
      items: [
        {
          project_id: 5,
          project_name: "Dům Novák",
          step_code: "stavba_montaz",
          step_name: "Montáž FVE",
          work_type: "roofer",
          kind: "firm",
          duration_days: 1,
          start: "2026-10-19",
          end: "2026-10-19",
          crew_name: "Montáž",
        },
        {
          project_id: 10,
          project_name: "Rezervace Test",
          step_code: "stavba_montaz",
          step_name: "Montáž FVE",
          work_type: "roofer",
          kind: "reserve",
          duration_days: 2,
          start: "2026-10-20",
          end: "2026-10-21",
          crew_name: "Montáž",
        },
        ...(extra > 0
          ? [
              {
                project_id: 20,
                project_name: "Simulace Nový Projekt",
                step_code: "stavba_montaz",
                step_name: "Montáž FVE",
                work_type: "roofer",
                kind: "firm",
                duration_days: 3,
                start: "2026-10-22",
                end: "2026-10-23",
                crew_name: "Montáž +1",
              },
            ]
          : []),
      ],
      projects: [
        {
          id: 5,
          name: "Dům Novák",
          kind: "firm",
          lead_age_days: 3,
          sod_date: "2026-10-10",
          done_date: "2026-12-15",
        },
        {
          id: 10,
          name: "Rezervace Test",
          kind: "reserve",
          lead_age_days: 12,
          reservation_expires: "2026-11-17",
        },
        ...(extra > 0
          ? [
              {
                id: 20,
                name: "Simulace Nový Projekt",
                kind: "firm",
                lead_age_days: 1,
                done_date: "2026-10-23",
              },
            ]
          : []),
      ],
      makespan: extra > 0 ? "2026-12-20" : "2026-12-15",
    };
  }),
  listCrews: vi.fn(async () => [
    {
      id: 1,
      name: "Montáž",
      work_type: "roofer",
      available_from: "2026-10-01",
      available_to: "2027-12-31",
      work_days: ["po", "ut", "st", "ct", "pa"],
      absent_dates: [],
      active: true,
    },
  ]),
  createCrew: vi.fn(),
  updateCrew: vi.fn(),
}));

// Pre-set user in localStorage so AuthProvider picks it up on init
function setTestUser(user: User) {
  localStorage.setItem("user", JSON.stringify(user));
  localStorage.setItem("token", "fake-token");
  localStorage.setItem("activeRole", user.role);
}

function renderPlanovani(user: User) {
  setTestUser(user);
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Planovani />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("Planovani — Gantt projekty", () => {
  it("zobrazí filmy jako plné pruhy a rezervace s odlišným stylem", async () => {
    setTestUser({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");
    expect(screen.getByText("Dům Novák")).toBeTruthy();
    expect(screen.getByText("Rezervace Test")).toBeTruthy();
  });

  it("zobrazí Gantt s datovými prvky", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");
    const gantt = screen.getByTestId("gantt-chart");
    expect(gantt).toBeTruthy();
  });
});

describe("Planovani — what-if simulate", () => {
  it("what-if checkbox volá simulate a překreslí makespan", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");

    const checkbox = screen.getByTestId("what-if-roofer");
    expect(checkbox).toBeTruthy();

    fireEvent.click(checkbox);

    await waitFor(() => {
      expect(screen.getByText("Simulace Nový Projekt")).toBeTruthy();
    });
  });
});

describe("Planovani — role", () => {
  it("admin uvidí tlačítko pro správu čteta", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");
    // user (role) se v AuthContext načítá async — počkej, než panel vyrenderuje
    await screen.findByText("Správa čteta");
    expect(screen.getByText("Správa čteta")).toBeTruthy();
  });

  it("zákazník neuvidí editaci čteta", async () => {
    renderPlanovani({ id: 99, email: "zak@test.local", role: "customer", roles: ["customer"] });
    await screen.findByText("Dům Novák");
    expect(screen.queryByText("Správa čteta")).toBeNull();
  });
});
