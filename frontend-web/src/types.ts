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
  assigned_name?: string | null;
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
  category?: string;
  visibility?: string;
  rating?: number | null;
  is_default?: boolean;
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
// ---------- fveAnalysis ----------
// Backend: backend/app/reportgen/fve_router.py

export interface FveParams {
  kwp: number;
  battery_capacity: number;
  annual_consumption_mwh: number;
  price_power: number;
  price_distribution: number;
  price_sell: number;
  sell_price_scheme: "fixed" | "community" | "shared" | "spot";
  community_sell_price: number;
  shared_sell_price: number;
  spot_price_margin: number;
  latitude: number;
  longitude: number;
  surface_tilt: number;
  surface_azimuth: number;
  /** null = bez limitu exportu. Backend to rozlišuje od 0 (limit nula). */
  grid_export_limit_kw: number | null;
  system_loss_factor: number;
  winter_loss_factor: number;
  thermal_battery_capacity_kwh: number;
  thermal_battery_charge_power_kw: number;
  active_appliances: string[];
  bom_mode: "system" | "components";
  fve_materials: FveMaterialLine[];
  panel_material_id: number | null;
  inverter_material_id: number | null;
  battery_material_id: number | null;
  install_material_id: number | null;
  system_material_id: number | null;
  /** Volba a pořadí oddílů PDF per varianta (perzistuje se v fve_params_json). */
  pdf_sections?: PdfSectionsConfig;
}

/** Varianta PDF reportu: `customer` = nabídka, `company` = interní. */
export type PdfVariant = "customer" | "company";

/** Volba oddílů PDF zvlášť pro obě varianty (id z registru oddílů). */
export interface PdfSectionsConfig {
  customer?: string[];
  company?: string[];
}

/** Metadata oddílu PDF z `GET /fve-analysis/report/sections`. */
export interface ReportSectionMeta {
  id: string;
  label: string;
  description: string;
  base: boolean;
}

/** Jedna položka snímku sestavy, uložená v `fve_params_json`.
 *  Stejný tvar vrací i `run_economic_analysis` v `investment_breakdown`
 *  (proto volitelné `name`/`rating` — řádek rozpadu investice je může nést). */
export interface FveMaterialLine {
  material_id: number;
  code: string;
  name?: string;
  category: string;
  rating?: number | null;
  unit?: string;
  qty: number;
  unit_price: number;
  line_total: number;
}

/** Katalog pro přepínač sestavy. Server skryje `internal` zákazníkovi. */
export interface FveMaterial {
  id: number;
  code: string;
  name: string;
  category: "panel" | "inverter" | "battery" | "install" | "system" | "other";
  visibility: "public" | "internal";
  rating?: number | null;
  unit?: string;
  price: number;
  is_default?: boolean;
  system_kwp?: number | null;
  system_battery_kwh?: number | null;
}

export interface FveAppliance {
  name: string;
  power_kw: number;
  type: string;
  description: string;
}

export interface FveGeocodeResult {
  latitude: number;
  longitude: number;
  display_name: string;
}

export interface FveAnalysisResult {
  kwp: number;
  latitude: number;
  longitude: number;
  battery_capacity: number;
  annual_consumption_mwh: number;
  financial_balance: {
    annual_savings_czk: number;
    cost_without_pv_czk: number;
    cost_with_pv_czk: number;
  };
  energy_balance_kwh: {
    total_consumption: number;
    grid_import: number;
    grid_export: number;
    self_consumption: number;
  };
  economic_balance_czk: {
    cost_total_consumption: number;
    cost_import: number;
    revenue_export: number;
    savings_self_consumption: number;
  };
  production_details: {
    total_production_actual: number;
    total_production_optimal: number;
    production_performance_pct: number;
  };
  /** Každý graf je JSON STRING — backend volá plotly.io.to_json().
   *  PlotlyChart ho parsuje. Kdyby tu byl objekt, graf by přestal fungovat
   *  bez jakékoli chyby. */
  plots: Record<string, string>;
  appliance_metrics: Record<string, {
    fve_kWh: number;
    grid_kWh: number;
    total_kWh: number;
    savings_czk: number;
    grid_cost_czk: number;
    operating_hours: number;
    coverage_pct: number;
  }>;
  appliance_details: FveAppliance[];
  recommendations: string[];
  monthly_summary: Array<Record<string, number | string>>;
  appliance_monthly_summary: Array<Record<string, number | string>>;
  raw_data: unknown;
}

export interface FveEconomicResult {
  metrics: {
    payback_years: number | string;
    discounted_payback_years: number | string;
    npv_czk: number;
    final_pv_gain_czk: number;
    final_pv_reinvest_gain_czk: number;
    final_sp500_net_czk: number;
  };
  investment_cost: number;
  investment_breakdown: FveMaterialLine[];
  plot: string | null;
  raw_data: Array<Record<string, number>>;
}

export interface FveContact {
  name: string;
  email: string;
  phone: string;
}

export interface SavedAnalysis {
  id: number;
  status: string;
  share_code: string;
  customer_id: number;
  /** true = právě vznikl uživatelský účet pro tento kontakt */
  customer_created: boolean;
}
