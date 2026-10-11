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
  const projectNoTemplate = { id: 2, name: "K2", type: "byt", status: "active", customer_name: "Malý" };
  return {
    listProjects: vi.fn(async () => [project, projectNoTemplate]),
    getPipeline: vi.fn(async (id: number | string) => ({
      project: Number(id) === 2 ? projectNoTemplate : project,
      template: null,
      steps: Number(id) === 2 ? [] : steps,
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
    expect(within(screen.getAllByTestId("cell-lead")[0]).getAllByRole("link")).toHaveLength(2);
    expect(within(screen.getAllByTestId("cell-realizace")[0]).getAllByRole("link")).toHaveLength(1);
    expect(within(screen.getAllByTestId("cell-nezarazeno")[0]).getAllByRole("link")).toHaveLength(2);
    expect(within(screen.getAllByTestId("cell-smlouva")[0]).queryAllByRole("link")).toHaveLength(0);
  });

  it("odkaz čtverečku míří na pipeline s fází a konkrétním krokem", async () => {
    renderBoard();
    await screen.findByText("K1");
    const links = within(screen.getAllByTestId("cell-lead")[0]).getAllByRole("link");
    expect(links[0].getAttribute("href")).toBe("/projects/1/pipeline?phase=lead&stepId=11");
  });

  it("hover nad čtverečkem zobrazí název aktivity v tooltipu", async () => {
    renderBoard();
    await screen.findByText("K1");
    const link = within(screen.getAllByTestId("cell-lead")[0]).getAllByRole("link")[0];
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.mouseEnter(link.parentElement!);
    expect(screen.getByRole("tooltip").textContent).toContain("Poptávka");
  });

  it("projekt bez šablony hlásí „bez šablony“ ve sloupci LEAD", async () => {
    renderBoard();
    const row = (await screen.findByText("K2")).closest("tr")!;
    expect(within(row).getByTestId("cell-lead").textContent).toContain("bez šablony");
    // jediné odkaz v řádku je název zakázky, žádné čtverečky
    expect(within(row).getAllByRole("link")).toHaveLength(1);
  });
});
