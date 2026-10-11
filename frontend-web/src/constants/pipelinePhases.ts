// Sloupce/sub-taby dispečinkové tabule odvozené z fází pipeline kroků.
// Fáze (`PipelineStep.phase`) žijí v DB (pipeline_steps.phase). Kanonické
// hlavní fáze mají vlastní sloupec; vše ostatní (včetně nově definovaných fází
// v DB) se automaticky zařadí do "Nezařazeno".
import type { PipelineStep } from "../types";

/** Kanonické klíče sloupců; nová DB fáze bez mapování → "nezarazeno". */
export type BoardPhaseKey =
  | "lead"
  | "priprava"
  | "smlouva"
  | "realizace"
  | "predani"
  | "revize"
  | "nezarazeno"
  | "final";

export interface BoardPhase {
  key: BoardPhaseKey;
  label: string;
}

export const BOARD_PHASES: BoardPhase[] = [
  { key: "lead", label: "LEAD" },
  { key: "priprava", label: "Příprava" },
  { key: "smlouva", label: "Smlouva" },
  { key: "realizace", label: "Realizace" },
  { key: "predani", label: "Předání" },
  { key: "revize", label: "Revize" },
  { key: "nezarazeno", label: "Nezařazeno" },
  { key: "final", label: "Finální" },
];

const MAIN_KEYS = new Set<string>(BOARD_PHASES.map((p) => p.key));

/** Hlavní sloupec pro fázi kroku; neznámá/nová fáze → Nezařazeno. */
export function mainPhaseOf(phase: string): BoardPhaseKey {
  return MAIN_KEYS.has(phase) ? (phase as BoardPhaseKey) : "nezarazeno";
}

export function boardPhaseLabel(key: BoardPhaseKey): string {
  return BOARD_PHASES.find((p) => p.key === key)?.label ?? key;
}

/** Seskupí kroky do všech 8 sloupců (i prázdných), uvnitř podle `order`. */
export function groupStepsByBoardPhase(
  steps: PipelineStep[],
): Array<[BoardPhaseKey, PipelineStep[]]> {
  const map = new Map<BoardPhaseKey, PipelineStep[]>();
  for (const p of BOARD_PHASES) map.set(p.key, []);
  for (const s of steps) map.get(mainPhaseOf(s.phase))!.push(s);
  for (const arr of map.values()) arr.sort((a, b) => a.order - b.order);
  return Array.from(map.entries());
}
