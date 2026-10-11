import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../context/AuthContext";
import PipelineDetail from "./PipelineDetail";

vi.mock("../api/pipeline", () => {
  const steps = [
    { id: 1, code: "L1", name: "Poptávka", phase: "lead", order: 1, status: "done", can: [] },
    { id: 5, code: "R1", name: "Montáž", phase: "realizace", order: 10, status: "in_progress", can: ["begin"] },
    { id: 6, code: "T1", name: "Odeslání přetoků", phase: "pretoky", order: 20, status: "not_started", can: [] },
  ];
  const project = { id: 1, name: "K1", type: "rd", status: "active", customer_name: "Novák" };
  return {
    // Testy pomalého načtení nastaví (globalThis as any).__pipelineLoadDelay.
    getPipeline: vi.fn(async () => {
      const delay = (globalThis as Record<string, unknown>).__pipelineLoadDelay as number | undefined;
      if (delay) await new Promise((r) => setTimeout(r, delay));
      return { project, template: null, steps, events: [], groups: [] };
    }),
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
    await act(async () => {}); // flush render z deep-link efektu
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

  it("scroll k cílovému kroku proběhne jen jednou, ani po akci na krok", async () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    renderDetail("/projects/1/pipeline?phase=realizace&stepId=5");
    await screen.findByText("Montáž");
    expect(scrollSpy).toHaveBeenCalledTimes(1);
    // akce volá refresh() → nový view → scroll se NESMÍ zopakovat
    fireEvent.click(screen.getByRole("button", { name: "Začít" }));
    await screen.findByText(/Začít OK/);
    expect(scrollSpy).toHaveBeenCalledTimes(1);
  });

  it("zvýraznění běží 3 s od načtení dat a pak zmizí", async () => {
    vi.useFakeTimers();
    (globalThis as Record<string, unknown>).__pipelineLoadDelay = 3200;
    try {
      Element.prototype.scrollIntoView = vi.fn();
      renderDetail("/projects/1/pipeline?phase=realizace&stepId=5");
      // data dorazí ve 3,2 s – zvýraznění musí být stále vidět (počítáno od načtení)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3300);
      });
      expect(document.querySelector('[data-step-id="5"]')?.getAttribute("data-highlighted")).toBe("true");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3100);
      });
      expect(document.querySelector('[data-step-id="5"]')?.getAttribute("data-highlighted")).toBeNull();
    } finally {
      delete (globalThis as Record<string, unknown>).__pipelineLoadDelay;
      vi.useRealTimers();
    }
  });

  it("neplatný ?phase zobrazí všechny sekce", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderDetail("/projects/1/pipeline?phase=nesmysl");
    await screen.findByText("Montáž");
    expect(screen.getByText("Poptávka")).toBeTruthy();
    expect(screen.getByText("Odeslání přetoků")).toBeTruthy();
  });

  it("?stepId bez ?phase zvýrazní krok a scrolluje", async () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    renderDetail("/projects/1/pipeline?stepId=5");
    await screen.findByText("Montáž");
    await act(async () => {}); // flush render z deep-link efektu
    expect(screen.getByText("Poptávka")).toBeTruthy();
    expect(document.querySelector('[data-step-id="5"]')?.getAttribute("data-highlighted")).toBe("true");
    expect(scrollSpy).toHaveBeenCalledTimes(1);
  });

  it("chybný ?stepId stránku nerozbije", async () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    // v prohlížeči hodí querySelector na špatný selektor SyntaxError →
    // selektor se nesmí nikdy dostat do DOM API
    const qsSpy = vi.spyOn(document, "querySelector");
    renderDetail('/projects/1/pipeline?phase=realizace&stepId=1%22');
    await screen.findByText("Montáž");
    expect(scrollSpy).not.toHaveBeenCalled();
    expect(qsSpy).not.toHaveBeenCalledWith('[data-step-id="1""]');
    qsSpy.mockRestore();
  });

  it("prázdný tab fáze zobrazí oznamovací lištu", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    renderDetail("/projects/1/pipeline");
    await screen.findByText("Montáž");
    fireEvent.click(screen.getByRole("button", { name: "Smlouva" }));
    await screen.findByText("Žádné kroky v této fázi.");
  });
});
