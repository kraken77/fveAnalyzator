// API klient pro procesní pipeline (Dispečink) — volání přes axios client
import client from "./client";
import type {
  InvoiceItem,
  Material,
  MaterialBalanceRow,
  Notification,
  PipelineEvent,
  PipelineTemplate,
  PipelineView,
  ProjectEconomy,
  ProjectLite,
  ProjectMaterial,
  TemplateStep,
  TimeEntry,
  TimeSummary,
} from "../types";

// ---------- Projekty / pipeline ----------

export async function listProjects(): Promise<ProjectLite[]> {
  const res = await client.get("/projects");
  return res.data as ProjectLite[];
}

export async function getPipeline(projectId: number | string): Promise<PipelineView> {
  const res = await client.get(`/projects/${projectId}/pipeline`);
  return res.data as PipelineView;
}

export interface TransitionBody {
  action: string;
  note?: string | null;
  plan_date?: string | null;
  assigned_user_id?: number | string | null;
}

export async function transitionStep(
  projectId: number | string,
  stepId: number | string,
  body: TransitionBody,
): Promise<{ status: string; id: number | string }> {
  const res = await client.post(`/projects/${projectId}/steps/${stepId}/transition`, body);
  return res.data;
}

export async function adminTransitionStep(
  projectId: number | string,
  stepId: number | string,
  body: {
    action: string;
    note?: string | null;
    plan_date?: string | null;
    assigned_user_id?: number | string | null;
    real_admin_minutes?: number;
    real_work_minutes?: number;
    to_status?: string | null;
  },
): Promise<{ status?: string; action?: string; id: number | string }> {
  const res = await client.post(`/projects/${projectId}/steps/${stepId}/admin`, body);
  return res.data;
}

export async function attachTemplate(
  projectId: number | string,
  templateCode: string,
): Promise<{ status: string; template_id?: number | string }> {
  const res = await client.post(`/projects/${projectId}/pipeline/attach`, {
    template_code: templateCode,
  });
  return res.data;
}

// ---------- AI ----------

export async function runAI(
  projectId: number | string,
  stepId: number | string,
  trigger: "auto" | "manual" = "manual",
): Promise<{ id: number | string; status: string; kind: string }> {
  const res = await client.post(`/projects/${projectId}/steps/${stepId}/run-ai`, { trigger });
  return res.data;
}

export async function reviewAI(
  projectId: number | string,
  stepId: number | string,
  resultId: number | string,
  approved: boolean,
  note?: string,
): Promise<{ id: number | string; status: string; step_status: string }> {
  const res = await client.post(`/projects/${projectId}/steps/${stepId}/review-ai`, {
    result_id: resultId,
    approved,
    note,
  });
  return res.data;
}

export async function getAiResults(
  projectId: number | string,
  stepId: number | string,
): Promise<Array<{ id: number | string; kind?: string; status?: string; output?: Record<string, unknown>; created_at?: string | null }>> {
  const res = await client.get(`/projects/${projectId}/steps/${stepId}/ai-results`);
  return res.data;
}

// ---------- Časové výkazy ----------

export async function getTimeEntries(projectId: number | string): Promise<TimeEntry[]> {
  const res = await client.get(`/projects/${projectId}/time-entries`);
  return res.data as TimeEntry[];
}

export async function addTimeEntry(
  projectId: number | string,
  body: {
    step_id?: number | string | null;
    minutes: number;
    work_date?: string | null;
    kind: "admin" | "work";
    note?: string;
  },
): Promise<TimeEntry> {
  const res = await client.post(`/projects/${projectId}/time-entries`, body);
  return res.data as TimeEntry;
}

export async function getTimeSummary(projectId: number | string): Promise<TimeSummary> {
  const res = await client.get(`/projects/${projectId}/time-entries/summary`);
  return res.data as TimeSummary;
}

export function monteriCsvUrl(from: string, to: string): string {
  const base = client.defaults.baseURL || "/api/v1";
  return `${base}/admin/reports/monteri-csv?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
}

// ---------- Materiály ----------

export async function getMaterials(): Promise<Material[]> {
  const res = await client.get("/materials");
  return res.data as Material[];
}

export async function addMaterial(body: {
  code: string;
  name: string;
  unit?: string;
  price?: number;
}): Promise<Material> {
  const res = await client.post("/materials", body);
  return res.data as Material;
}

export async function getProjectMaterials(projectId: number | string): Promise<ProjectMaterial[]> {
  const res = await client.get(`/projects/${projectId}/materials`);
  return res.data as ProjectMaterial[];
}

export async function addProjectMaterial(
  projectId: number | string,
  body: {
    material_id: number | string;
    qty: number;
    lane: string;
    step_id?: number | string | null;
    price_snapshot?: number | null;
  },
): Promise<ProjectMaterial> {
  const res = await client.post(`/projects/${projectId}/materials`, body);
  return res.data as ProjectMaterial;
}

export async function getMaterialsBalance(
  projectId: number | string,
): Promise<MaterialBalanceRow[]> {
  const res = await client.get(`/projects/${projectId}/materials/balance`);
  return res.data as MaterialBalanceRow[];
}

// ---------- Fakturace / ekonomika ----------

export async function getInvoiceItems(projectId: number | string): Promise<InvoiceItem[]> {
  const res = await client.get(`/projects/${projectId}/invoice-items`);
  return res.data as InvoiceItem[];
}

export async function addInvoiceItem(
  projectId: number | string,
  body: { doc_type: string; description?: string; amount_czk: number },
): Promise<InvoiceItem> {
  const res = await client.post(`/projects/${projectId}/invoice-items`, body);
  return res.data as InvoiceItem;
}

export async function setInvoiceStatus(
  projectId: number | string,
  itemId: number | string,
  status: "issued" | "paid",
): Promise<{ id: number | string; status: string; doc_number?: string | null }> {
  const res = await client.post(`/projects/${projectId}/invoice-items/${itemId}/status`, {
    status,
  });
  return res.data;
}

// ---------- Šablony (admin) ----------

export async function getTemplates(): Promise<PipelineTemplate[]> {
  const res = await client.get("/admin/pipeline-templates");
  return res.data as PipelineTemplate[];
}

export async function getTemplateSteps(
  templateId: number | string,
): Promise<TemplateStep[]> {
  const res = await client.get(`/admin/pipeline-templates/${templateId}/steps`);
  return res.data as TemplateStep[];
}

export async function updateTemplateStep(
  templateId: number | string,
  stepId: number | string,
  body: Partial<Pick<TemplateStep, "name" | "est_admin_minutes" | "est_work_minutes">>,
): Promise<{ status: string }> {
  const res = await client.put(
    `/admin/pipeline-templates/${templateId}/steps/${stepId}`,
    body,
  );
  return res.data;
}

export async function importDispecink(file: File): Promise<{ status: string; imported?: number; skipped?: number }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await client.post("/admin/import/dispecink", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

// ---------- Notifikace ----------

export async function getNotifications(): Promise<Notification[]> {
  const res = await client.get("/notifications");
  return res.data as Notification[];
}

export async function readNotification(
  id: number | string,
): Promise<{ id: number | string; read: boolean }> {
  const res = await client.post(`/notifications/${id}/read`);
  return res.data;
}

// ---------- Uživatelé / sazby (admin) ----------

export async function adminListUsers(): Promise<
  Array<{ id: number | string; email: string; role: string; roles?: string[]; created_at?: string | null }>
> {
  const res = await client.get("/admin/users");
  return res.data;
}

export async function adminSetUserRoles(
  userId: number | string,
  roles: string[],
): Promise<{ status: string; roles: string[] }> {
  const res = await client.put(`/admin/users/${userId}/roles`, { roles });
  return res.data;
}

// ---------- Economy (volitelné — server computed) ----------

export async function getProjectEconomy(projectId: number | string): Promise<ProjectEconomy | null> {
  try {
    const res = await client.get(`/projects/${projectId}/economy`);
    return res.data as ProjectEconomy;
  } catch {
    return null;
  }
}

export type { PipelineEvent };