// API klient pro Plánování montáže a elektro — volání přes axios client
import client from "./client";

// ---------- Typy ----------

export interface WorkCrew {
  id: number;
  name: string;
  work_type: string;
  available_from: string;
  available_to: string;
  work_days: string[];
  absent_dates: string[];
  active: boolean;
}

export interface PlanningItem {
  project_id: number | string;
  project_name: string;
  step_code: string;
  step_name: string;
  work_type: string;
  kind: "firm" | "reserve" | "expired";
  duration_days: number;
  start: string | null;
  end: string | null;
  crew_name: string | null;
}

export interface PlanningProject {
  id: number | string;
  name: string;
  kind: "firm" | "reserve" | "expired";
  lead_age_days?: number;
  reservation_expires?: string | null;
  done_date?: string | null;
  sod_date?: string | null;
}

export interface PlanningOverview {
  today: string;
  holidays_in_range: string[];
  ttl_days: number;
  makespan: string | null;
  crews: WorkCrew[];
  items: PlanningItem[];
  projects: PlanningProject[];
}

export interface SimulateResponse {
  items: PlanningItem[];
  projects: PlanningProject[];
  makespan: string | null;
}

export interface SimulateBody {
  add_crews: Record<string, number>;
}

// ---------- Funkce ----------

export async function getOverview(
  from: string,
  to: string,
): Promise<PlanningOverview> {
  const res = await client.get("/planning/overview", {
    params: { from, to },
  });
  return res.data as PlanningOverview;
}

export async function simulate(
  body: SimulateBody,
): Promise<SimulateResponse> {
  const res = await client.post("/planning/simulate", body);
  return res.data as SimulateResponse;
}

export async function listCrews(): Promise<WorkCrew[]> {
  const res = await client.get("/planning/crews");
  return res.data as WorkCrew[];
}

export async function createCrew(body: Partial<WorkCrew>): Promise<WorkCrew> {
  const res = await client.post("/planning/crews", body);
  return res.data as WorkCrew;
}

export async function updateCrew(
  crewId: number | string,
  body: Partial<WorkCrew>,
): Promise<WorkCrew> {
  const res = await client.put(`/planning/crews/${crewId}`, body);
  return res.data as WorkCrew;
}
