import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../context/AuthContext";
import type { User } from "../context/AuthContext";
import { getOverview, simulate } from "../api/planning";
import type { PlanningOverview } from "../api/planning";
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
      crews: [
        { name: "Montáž", work_type: "roofer", virtual: false },
        ...(extra > 0
          ? [
              { name: "Montáž +1", work_type: "roofer", virtual: true },
              { name: "Montáž +2", work_type: "roofer", virtual: true },
            ]
          : []),
      ],
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
  it("what-if počet čteta volá simulate a překreslí makespan", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");

    const input = screen.getByTestId("what-if-roofer");
    fireEvent.change(input, { target: { value: "2" } });

    await waitFor(() => {
      expect(screen.getByText("Simulace Nový Projekt")).toBeTruthy();
    });
    expect(simulate).toHaveBeenCalledWith({ add_crews: { roofer: 2 } });
  });

  it("simulace ukáže složení čteta v KPI souhrnu", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");

    fireEvent.change(screen.getByTestId("what-if-roofer"), {
      target: { value: "2" },
    });
    await screen.findByText("Simulace Nový Projekt");
    // 1 základní + 2 virtuální montáže
    expect(screen.getByText("3 Montáž")).toBeTruthy();
  });

  it("virtuální četa je v Gantu označená pruhovaným rámem", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");

    fireEvent.change(screen.getByTestId("what-if-roofer"), {
      target: { value: "1" },
    });
    const bar = await screen.findByText("(Montáž +1)");
    const ganttBar = bar.closest("div.absolute");
    expect(ganttBar?.className).toContain("border-dashed");
  });
});

describe("Planovani — Gantt zoom a skok", () => {
  it("zoom týdny ukáže týdenní rozsahy", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");

    fireEvent.click(screen.getByRole("button", { name: "Týdny" }));
    // 19.–25.10.2026 = první celý týden od dneška (2026-10-18 = So)
    await screen.findByText("19.–25.10.");
  });

  it("skok do období posune Gantt", async () => {
    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");
    // jsdom neimplementuje scrollTo — doplním ho přímo na scroll container
    const gantt = screen.getByTestId("gantt-chart");
    const scrollSpy = vi.fn();
    (
      gantt as unknown as { scrollTo: (opts: { left: number; behavior: string }) => void }
    ).scrollTo = scrollSpy;

    fireEvent.change(screen.getByTestId("gantt-jump-date"), {
      target: { value: "2026-12-01" },
    });
    fireEvent.click(screen.getByTestId("gantt-jump"));
    expect(scrollSpy).toHaveBeenCalled();
  });
});

describe("Planovani — svátky v celém rozsahu gantu", () => {
  it("při makespanu delším než 90 dní doženou svátky na celý rozsah", async () => {
    const narrow: PlanningOverview = {
      today: "2026-10-18",
      holidays_in_range: ["2026-11-01"],
      ttl_days: 30,
      makespan: "2027-03-24",
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
          step_name: "Montáž",
          work_type: "roofer",
          kind: "firm",
          duration_days: 10,
          start: "2027-03-10",
          end: "2027-03-24",
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
          done_date: "2027-03-24",
        },
      ],
    };
    const wide: PlanningOverview = {
      ...narrow,
      holidays_in_range: [
        "2026-11-01",
        "2026-12-25",
        "2027-01-01",
        "2027-02-09",
      ],
    };
    vi.mocked(getOverview)
      .mockResolvedValueOnce(narrow)
      .mockResolvedValueOnce(wide);

    renderPlanovani({ id: 1, email: "admin@test.local", role: "admin", roles: ["admin"] });
    await screen.findByText("Dům Novák");

    const kpi = () =>
      screen.getByText("Svátky v období").closest(".kpi-card") as HTMLElement;
    expect(kpi().textContent).toContain("1");

    // makespan 2027-03-24 → konec gantu 2027-03-31 → tichý re-fetch s větším „to“
    await waitFor(() => expect(kpi().textContent).toContain("4"));
    expect(getOverview).toHaveBeenLastCalledWith("2026-10-18", "2027-03-31");
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
