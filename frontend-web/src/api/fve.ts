import client from "./client";
import type {
  FveAnalysisResult,
  FveAppliance,
  FveContact,
  FveEconomicResult,
  FveGeocodeResult,
  FveMaterial,
  FveParams,
  SavedAnalysis,
} from "../types";

/** Backend přijímá jen to, co uživatel změnil — zbytek doplní default. */
export const runAnalysis = (params: Partial<FveParams>) =>
  client
    .post<FveAnalysisResult>("/fve-analysis/run", params)
    .then((r) => r.data);

export const runEconomic = (params: Record<string, unknown>) =>
  client
    .post<FveEconomicResult>("/fve-analysis/economic", params)
    .then((r) => r.data);

/** Nominatim hledá adresu i obec a vrací VÍC kandidátů k výběru. */
export const geocode = (address: string) =>
  client
    .post<{ results: FveGeocodeResult[] }>("/fve-analysis/geocode", { address })
    .then((r) => r.data.results);

export const fetchAppliances = () =>
  client
    .get<{ appliances: FveAppliance[] }>("/fve-analysis/appliances")
    .then((r) => r.data.appliances);

export const saveAnalysis = (params: FveParams, contact: FveContact, name?: string) =>
  client
    .post<SavedAnalysis>("/fve-analysis", { params, contact, name })
    .then((r) => r.data);

/** Jen admin/antelon. Po převodu je projekt ve stavu lead a má pipeline. */
export const convertToOrder = (projectId: number | string) =>
  client
    .post<{ id: number; status: string; type: string }>(
      `/projects/${projectId}/convert-to-order`,
    )
    .then((r) => r.data);

/** PDF jako blob — ne JSON, takže responseType: "blob".
 *  Ekonomika je volitelná; když chybí, PDF ji vynechá (chování jako dřív). */
export const downloadEnergyPdf = (
  energy: FveAnalysisResult,
  economic: FveEconomicResult | null,
) =>
  client.post(
    "/fve-analysis/report/energy",
    { energy, economic },
    { responseType: "blob" },
  );

/** Katalog pro přepínač sestavy. Server filtruje `internal` podle role. */
export const fetchFveMaterials = () =>
  client
    .get<{ materials: FveMaterial[] }>("/fve-analysis/materials")
    .then((r) => r.data.materials);

/** Defaulty musí sedět s backendem (FveParams v fve_router.py). */
export const DEFAULT_FVE_PARAMS: FveParams = {
  kwp: 10.0,
  battery_capacity: 10.0,
  annual_consumption_mwh: 5.0,
  price_power: 3.0,
  price_distribution: 2.0,
  price_sell: 2.0,
  sell_price_scheme: "fixed",
  community_sell_price: 1.5,
  shared_sell_price: 2.54,
  spot_price_margin: 0.4,
  latitude: 50.6607,
  longitude: 14.03227,
  surface_tilt: 35,
  surface_azimuth: 180,
  grid_export_limit_kw: 10.0,
  system_loss_factor: 14.0,
  winter_loss_factor: 10.0,
  thermal_battery_capacity_kwh: 0.0,
  thermal_battery_charge_power_kw: 2.0,
  active_appliances: [],
  bom_mode: "components",
  fve_materials: [],
  panel_material_id: null,
  inverter_material_id: null,
  battery_material_id: null,
  install_material_id: null,
  system_material_id: null,
};
