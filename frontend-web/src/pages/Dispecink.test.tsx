import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../context/AuthContext";
import Dispecink from "./Dispecink";

vi.mock("../api/pipeline", () => {
  const steps = [
    { id: 11, code: "L1", name: "Poptávka", phase: "lead", order: 1, status: "done" },
    { id: 12, code: "L2", name: "Schůzka", phase: "lead", order: 2, status: "planned" },
    { id: 13, code: "P1", name: "Výrobní dokumentace", phase: "priprava", order: 3, status: "not_started" },
    { id: 14, code: "R1", name: "Montáž", phase: "realizace", order: 10, status: "in_progress" },
    { id: 15, code: "T1", name: "Odeslání přetoků", phase: "pretoky", order: 20, status: "not_started" },
    { id: 16, code: "T2", name: "Vyúčtování přetoků", phase: "pretoky", order: 21, status: "planned" },
    { id: 17, code: "F1", name: "Závěrečná fakturace", phase: "final", order: 30, status: "not_started" },
  ];
  const project = { id: 1, name: "K1", type: "rd", status: "active", customer_name: "Novák" };
  return {
    listProjects: vi.fn(async () => [project]),
    getPipeline: vi.fn(async () => ({
      project,
      template: null,
      steps,
      events: [],
      groups: [],
    })),
    importDispecink: vi.fn(),
  };
});

function renderBoard() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Dispecink />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("Dispecink — sloupce fází", () => {
  it("zobrazí 8 sloupců fází místo jednoho sloupce Pipeline", async () => {
    renderBoard();
    await screen.findByText("K1");
    for (const label of [
      "LEAD",
      "Příprava",
      "Smlouva",
      "Realizace",
      "Předání",
      "Revize",
      "Nezařazeno",
      "Finální",
    ]) {
      expect(screen.getByRole("columnheader", { name: label })).toBeTruthy();
    }
    expect(screen.queryByRole("columnheader", { name: "Pipeline" })).toBeNull();
  });

  it("seskupí čtverečky po sloupcích a fázi pretoky dá do Nezařazeno", async () => {
    renderBoard();
    await screen.findByText("K1");
    expect(within(screen.getByTestId("cell-lead")).getAllByRole("link")).toHaveLength(2);
    expect(within(screen.getByTestId("cell-realizace")).getAllByRole("link")).toHaveLength(1);
    expect(within(screen.getByTestId("cell-nezarazeno")).getAllByRole("link")).toHaveLength(2);
    expect(within(screen.getByTestId("cell-smlouva")).queryAllByRole("link")).toHaveLength(0);
  });

  it("odkaz čtverečku míří na pipeline s fází a konkrétním krokem", async () => {
    renderBoard();
    await screen.findByText("K1");
    const links = within(screen.getByTestId("cell-lead")).getAllByRole("link");
    expect(links[0].getAttribute("href")).toBe("/projects/1/pipeline?phase=lead&stepId=11");
  });

  it("hover nad čtverečkem zobrazí název aktivity v tooltipu", async () => {
    renderBoard();
    await screen.findByText("K1");
    const link = within(screen.getByTestId("cell-lead")).getAllByRole("link")[0];
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.mouseEnter(link.parentElement!);
    expect(screen.getByRole("tooltip").textContent).toContain("Poptávka");
  });
});
