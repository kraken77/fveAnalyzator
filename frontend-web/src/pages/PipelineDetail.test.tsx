import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../context/AuthContext";
import PipelineDetail from "./PipelineDetail";

vi.mock("../api/pipeline", () => {
  const steps = [
    { id: 1, code: "L1", name: "Poptávka", phase: "lead", order: 1, status: "done", can: [] },
    { id: 5, code: "R1", name: "Montáž", phase: "realizace", order: 10, status: "in_progress", can: [] },
    { id: 6, code: "T1", name: "Odeslání přetoků", phase: "pretoky", order: 20, status: "not_started", can: [] },
  ];
  const project = { id: 1, name: "K1", type: "rd", status: "active", customer_name: "Novák" };
  return {
    getPipeline: vi.fn(async () => ({ project, template: null, steps, events: [], groups: [] })),
    getTimeEntries: vi.fn(async () => []),
    getTimeSummary: vi.fn(async () => null),
    getInvoiceItems: vi.fn(async () => []),
    getProjectEconomy: vi.fn(async () => null),
    adminListUsers: vi.fn(async () => []),
    transitionStep: vi.fn(async () => ({})),
    runAI: vi.fn(async () => ({ id: 0 })),
    reviewAI: vi.fn(async () => ({})),
    addTimeEntry: vi.fn(async () => ({})),
    addInvoiceItem: vi.fn(async () => ({})),
    setInvoiceStatus: vi.fn(async () => ({ doc_number: "X" })),
    monteriCsvUrl: vi.fn(() => "csv"),
  };
});

function renderDetail(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <Routes>
          <Route path="/projects/:id/pipeline" element={<PipelineDetail />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("PipelineDetail — sub-taby fází", () => {
  it("zobrazí sub-taby všech fází a bez parametru všechny sekce", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderDetail("/projects/1/pipeline");
    await screen.findByText("Montáž");
    for (const label of [
      "Vše",
      "LEAD",
      "Příprava",
      "Smlouva",
      "Realizace",
      "Předání",
      "Revize",
      "Nezařazeno",
      "Finální",
    ]) {
      expect(screen.getByRole("button", { name: label })).toBeTruthy();
    }
    expect(screen.getByText("Poptávka")).toBeTruthy();
    expect(screen.getByText("Odeslání přetoků")).toBeTruthy();
  });

  it("?phase=realizace zobrazí jen sekce patřící do Realizace", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderDetail("/projects/1/pipeline?phase=realizace");
    await screen.findByText("Montáž");
    expect(screen.queryByText("Poptávka")).toBeNull();
    expect(screen.queryByText("Odeslání přetoků")).toBeNull();
  });

  it("?stepId zvýrazní krok a scrolluje k němu", async () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    renderDetail("/projects/1/pipeline?phase=realizace&stepId=5");
    await screen.findByText("Montáž");
    const card = document.querySelector('[data-step-id="5"]');
    expect(card).toBeTruthy();
    expect(card!.getAttribute("data-highlighted")).toBe("true");
    expect(scrollSpy).toHaveBeenCalled();
  });

  it("klik na tab fáze filtruje sekce", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderDetail("/projects/1/pipeline");
    await screen.findByText("Montáž");
    fireEvent.click(screen.getByRole("button", { name: "LEAD" }));
    await screen.findByText("Poptávka");
    expect(screen.queryByText("Montáž")).toBeNull();
    expect(screen.queryByText("Odeslání přetoků")).toBeNull();
  });
});
