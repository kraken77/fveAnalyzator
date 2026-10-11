import { describe, expect, it } from "vitest";
import type { PipelineStep } from "../types";
import {
  BOARD_PHASES,
  boardPhaseLabel,
  groupStepsByBoardPhase,
  mainPhaseOf,
} from "./pipelinePhases";

function step(id: number, phase: string, order: number, name = `Krok ${id}`): PipelineStep {
  return { id, code: `c${id}`, name, phase, order, status: "not_started" };
}

describe("BOARD_PHASES", () => {
  it("má sloupce v kanonickém pořadí s Nezařazeno před Finální", () => {
    expect(BOARD_PHASES.map((p) => p.key)).toEqual([
      "lead",
      "priprava",
      "smlouva",
      "realizace",
      "predani",
      "revize",
      "nezarazeno",
      "final",
    ]);
  });

  it("popisuje sloupce českými labely (LEAD velice)", () => {
    expect(boardPhaseLabel("lead")).toBe("LEAD");
    expect(boardPhaseLabel("nezarazeno")).toBe("Nezařazeno");
    expect(boardPhaseLabel("final")).toBe("Finální");
  });
});

describe("mainPhaseOf", () => {
  it.each([
    ["lead", "lead"],
    ["priprava", "priprava"],
    ["smlouva", "smlouva"],
    ["realizace", "realizace"],
    ["predani", "predani"],
    ["revize", "revize"],
    ["final", "final"],
  ])("mapuje hlavní fázi %s na %s", (phase, expected) => {
    expect(mainPhaseOf(phase)).toBe(expected);
  });

  it("zařadí neznámou fázi (pretoky) do Nezařazeno", () => {
    expect(mainPhaseOf("pretoky")).toBe("nezarazeno");
  });

  it("zařadí novou fázi definovanou v DB automaticky do Nezařazeno", () => {
    expect(mainPhaseOf("zcela_nova_faze")).toBe("nezarazeno");
  });
});

describe("groupStepsByBoardPhase", () => {
  it("vrátí všech 8 skupin včetně prázdných", () => {
    const groups = groupStepsByBoardPhase([step(1, "lead", 1)]);
    expect(groups.map(([key, arr]) => [key, arr.length])).toEqual([
      ["lead", 1],
      ["priprava", 0],
      ["smlouva", 0],
      ["realizace", 0],
      ["predani", 0],
      ["revize", 0],
      ["nezarazeno", 0],
      ["final", 0],
    ]);
  });

  it("seskupí kroky podle hlavní fáze a seřadí je podle order", () => {
    const groups = groupStepsByBoardPhase([
      step(3, "pretoky", 30),
      step(2, "lead", 2),
      step(1, "lead", 1),
      step(4, "realizace", 10),
    ]);
    const byKey = new Map(groups);
    expect(byKey.get("lead")!.map((s) => s.id)).toEqual([1, 2]);
    expect(byKey.get("nezarazeno")!.map((s) => s.id)).toEqual([3]);
    expect(byKey.get("realizace")!.map((s) => s.id)).toEqual([4]);
  });
});
