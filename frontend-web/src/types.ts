// Typy pro procesní pipeline (Dispečink) — korespondují s API (M5)

export type PipelineStatus =
  | "not_started"
  | "planned"
  | "in_progress"
  | "done"
  | "signed"
  | "sent"
  | "skipped"
  | "cancelled"
  | "not_applicable";

export interface User {
  id: number | string;
  email: string;
  role: string;
  roles?: string[];
}

export interface ProjectLite {
  id: number | string;
  name: string;
  customer_name?: string;
  type?: string;
  status?: string;
  tech?: string | null;
  share_code?: string;
  owner_id?: number | string | null;
  updated_at?: string | null;
  antelon_params?: Record<string, unknown>;
  fve_params?: Record<string, unknown>;
}

export interface AiResult {
  id: number | string;
  kind?: string;
  status?: string;
  output?: Record<string, unknown>;
  input?: Record<string, unknown>;
  pdf_version_id?: number | string | null;
  reviewed_by?: number | string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
  created_by?: number | string | null;
}

export interface PipelineStep {
  id: number | string;
  pipeline_step_id?: number | string;
  code: string;
  name: string;
  phase: string;
  order: number;
  status: PipelineStatus;
  plan_date?: string | null;
  assigned_user_id?: number | string | null;
  note?: string | null;
  real_admin_minutes?: number;
  real_work_minutes?: number;
  est_admin_minutes?: number;
  est_work_minutes?: number;
  state_model?: string;
  hidden?: boolean;
  condition?: Record<string, unknown> | null;
  auto_hook?: string | null;
  parallel_group?: string | null;
  allowed_roles?: string[];
  ai?: AiResult | null;
  can?: string[];
}

export interface PipelineEvent {
  id: number | string;
  action: string;
  step: string;
  step_code?: string;
  from_status?: string;
  to_status?: string;
  user_id?: number | string | null;
  at?: string | null;
  note?: string | null;
}

export interface PipelineGroup {
  group: string;
  steps: Array<number | string>;
  done: boolean;
}

export interface PipelineView {
  project: ProjectLite;
  template?: {
    id: number | string;
    code: string;
    name: string;
    zakazka_type?: string;
    version?: number;
    active?: boolean;
  } | null;
  steps: PipelineStep[];
  events: PipelineEvent[];
  groups: PipelineGroup[];
}

export interface TemplateStep {
  id: number | string;
  code: string;
  name: string;
  phase: string;
  order: number;
  state_model?: string;
  condition?: Record<string, unknown> | null;
  auto_hook?: string | null;
  parallel_group?: string | null;
  allowed_roles?: string[];
  est_admin_minutes?: number;
  est_work_minutes?: number;
}

export interface PipelineTemplate {
  id: number | string;
  code: string;
  name: string;
  zakazka_type?: string;
  version?: number;
  active?: boolean;
}

export interface TimeEntry {
  id: number | string;
  step_id?: number | string | null;
  step_name?: string | null;
  user_email?: string | null;
  minutes: number;
  kind: "admin" | "work";
  work_date?: string | null;
  note?: string | null;
}

export interface TimeSummary {
  by_user: Record<string, { user_id: number | string; minutes: number; count: number }>;
  by_step: Record<string, { step_id: number | string | null; minutes: number; count: number }>;
  by_type: Record<string, { kind: string; minutes: number; count: number }>;
  total_minutes: number;
}

export interface Material {
  id: number | string;
  code: string;
  name: string;
  unit?: string;
  price?: number;
  active?: boolean;
}

export interface ProjectMaterial {
  id: number | string;
  material_id: number | string;
  code?: string;
  name?: string;
  lane: string;
  qty_planned?: number;
  qty_actual?: number;
  price_snapshot?: number;
  step_id?: number | string | null;
}

export interface MaterialBalanceRow {
  material_id: number | string;
  code: string;
  name: string;
  unit?: string;
  price: number;
  plan_qty: number;
  order_qty: number;
  issue_qty: number;
  actual_qty: number;
  total_plan_czk: number;
}

export interface InvoiceItem {
  id: number | string;
  doc_type: string;
  doc_number?: string | null;
  description?: string | null;
  amount_czk: number;
  status: string;
  step_id?: number | string | null;
  created_at?: string | null;
}

export interface Notification {
  id: number | string;
  text: string;
  project_id?: number | string | null;
  read: boolean;
  created_at?: string | null;
}

export interface ProjectEconomy {
  plan: {
    admin_minutes: number;
    admin_cost: number;
    work_minutes: number;
    work_cost: number;
    total_cost: number;
  };
  actual: {
    admin_minutes: number;
    admin_cost: number;
    work_minutes: number;
    work_cost: number;
    total_cost: number;
  };
  margin: number;
  sell: number;
  sell_actual: number;
}