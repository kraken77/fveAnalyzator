import { useEffect, useState } from "react";
import { fetchFveMaterials, geocode } from "../../api/fve";
import type {
  FveAppliance, FveGeocode, FveMaterial, FveMaterialLine, FveParams,
} from "../../types";

const SELL_SCHEMES = [
  { value: "fixed", label: "Fixní cena" },
  { value: "community", label: "Komunita" },
  { value: "shared", label: "Sdílení" },
  { value: "spot", label: "Spot" },
] as const;

function NumberField({
  label, unit, min, max, step = 0.1, value, onChange, help,
}: {
  label: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
  help?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm text-slate-700">{label}</span>
      <div className="flex items-center gap-2 mt-1">
        <input
          type="number"
          value={Number.isFinite(value) ? value : ""}
          min={min}
          max={max}
          step={step}
          onChange={(e) => {
            const n = Number(e.target.value);
            // prázdné pole není 0 — 0 kWp je nesmysl, prázdno je „ještě nevyplněno"
            onChange(e.target.value === "" ? NaN : n);
          }}
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
        />
        {unit && <span className="text-sm text-slate-500 w-12">{unit}</span>}
      </div>
      {help && <span className="text-xs text-slate-500">{help}</span>}
    </label>
  );
}

/** Tři dílčí karty místo jednoho dlouhého seznamu (spec 6.3). */
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-lg border border-slate-200">
      <h3 className="font-semibold text-navy px-5 py-3 border-b border-slate-100">{title}</h3>
      <div className="p-5 space-y-4">{children}</div>
    </section>
  );
}

/** Zrcadlo backendové `derive_qty` — musí počítat stejně, jinak se snímek
 *  a živý součet rozjedou. Backend je autoritativní při uložení. */
function deriveQty(category: string, rating: number | null | undefined, p: FveParams): number {
  if (category === "panel") return rating ? Math.ceil((p.kwp * 1000) / rating) : 0;
  if (category === "inverter") return rating ? Math.ceil(p.kwp / rating) : 0;
  if (category === "battery") return rating ? Math.ceil(p.battery_capacity / rating) : 0;
  return 1;
}

function buildBom(p: FveParams, mats: FveMaterial[]): FveMaterialLine[] {
  const byId = (id: number | null) => mats.find((m) => Number(m.id) === id);
  if (p.bom_mode === "system") {
    const m = byId(p.system_material_id);
    if (!m) return [];
    const price = Number(m.price ?? 0);
    return [{
      material_id: Number(m.id), code: m.code, category: m.category,
      qty: 1, unit_price: price, line_total: price,
    }];
  }
  const picks: Array<{ id: number | null; category: string }> = [
    { id: p.panel_material_id, category: "panel" },
    { id: p.inverter_material_id, category: "inverter" },
    { id: p.battery_material_id, category: "battery" },
    { id: p.install_material_id, category: "install" },
  ];
  const out: FveMaterialLine[] = [];
  for (const pick of picks) {
    const m = byId(pick.id);
    if (!m) continue;
    const qty = deriveQty(pick.category, m.rating, p);
    const price = Number(m.price ?? 0);
    out.push({
      material_id: Number(m.id), code: m.code, category: pick.category,
      qty, unit_price: price, line_total: qty * price,
    });
  }
  return out;
}

function MaterialSelect({
  label, value, options, onChange,
}: {
  label: string;
  value: number | null;
  options: FveMaterial[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-sm text-slate-700">{label}</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
      >
        <option value="">— nevybráno —</option>
        {options.map((m) => (
          <option key={m.id} value={m.id}>
            {m.code} — {m.name}{m.rating ? ` (${m.rating})` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

interface Props {
  params: FveParams;
  onChange: (next: FveParams) => void;
  appliances: FveAppliance[];
  onRun: () => void;
  running: boolean;
}

export default function FveAnalysisForm({
  params, onChange, appliances, onRun, running,
}: Props) {
  const [city, setCity] = useState("");
  const [geo, setGeo] = useState<FveGeocode | null>(null);
  const [geoError, setGeoError] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [materials, setMaterials] = useState<FveMaterial[]>([]);

  useEffect(() => {
    fetchFveMaterials().then(setMaterials).catch(() => setMaterials([]));
  }, []);

  // is_default předvyplní volbu, ale jen dokud uživatel nic nezvolil
  useEffect(() => {
    if (materials.length === 0) return;
    if (params.panel_material_id != null || params.system_material_id != null) return;
    const pick = (cat: string) =>
      materials.find((m) => m.category === cat && m.is_default) ?? null;
    const panel = pick("panel");
    const inverter = pick("inverter");
    const battery = pick("battery");
    const install = pick("install");
    const system = pick("system");
    const next: FveParams = {
      ...params,
      panel_material_id: panel ? Number(panel.id) : null,
      inverter_material_id: inverter ? Number(inverter.id) : null,
      battery_material_id: battery ? Number(battery.id) : null,
      install_material_id: install ? Number(install.id) : null,
      system_material_id: system ? Number(system.id) : null,
    };
    next.fve_materials = buildBom(next, materials);
    onChange(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materials]);

  const set = <K extends keyof FveParams>(key: K, value: FveParams[K]) => {
    const next = { ...params, [key]: value };
    if (materials.length > 0) next.fve_materials = buildBom(next, materials);
    onChange(next);
  };

  const setBomMaterial = (
    key: "panel_material_id" | "inverter_material_id" | "battery_material_id"
       | "install_material_id" | "system_material_id",
    raw: string,
  ) => {
    const id = raw === "" ? null : Number(raw);
    const next: FveParams = { ...params, [key]: id };
    if (key === "system_material_id" && id != null) {
      const m = materials.find((x) => Number(x.id) === id);
      // balíček předvyplní výkon/kapacitu; cena se PŘEPOČÍTÁVAT NEBUDE
      if (m?.system_kwp != null) next.kwp = m.system_kwp;
      if (m?.system_battery_kwh != null) next.battery_capacity = m.system_battery_kwh;
    }
    next.fve_materials = buildBom(next, materials);
    onChange(next);
  };

  const doGeocode = async () => {
    if (!city.trim()) {
      setGeoError("Zadejte název obce");
      return;
    }
    setGeocoding(true);
    setGeoError("");
    try {
      const r = await geocode(city.trim());
      setGeo(r);
      onChange({ ...params, latitude: r.latitude, longitude: r.longitude });
    } catch (e: any) {
      setGeo(null);
      setGeoError(e?.response?.data?.detail || "Místo se nepodařilo najít");
    } finally {
      setGeocoding(false);
    }
  };

  const toggleAppliance = (name: string, on: boolean) =>
    onChange({
      ...params,
      active_appliances: on
        ? [...params.active_appliances, name]
        : params.active_appliances.filter((n) => n !== name),
    });

  const panels = materials.filter((m) => m.category === "panel");
  const inverters = materials.filter((m) => m.category === "inverter");
  const batteries = materials.filter((m) => m.category === "battery");
  const installs = materials.filter((m) => m.category === "install");
  const systems = materials.filter((m) => m.category === "system");
  const investment = params.fve_materials.reduce((a, l) => a + l.line_total, 0);

  return (
    <div className="space-y-4">
      <Card title="Fotovoltaická elektrárna">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <NumberField label="Instalovaný výkon" unit="kWp" min={0.1} max={50}
                      value={params.kwp} onChange={(v) => set("kwp", v)} />
          <NumberField label="Kapacita baterie" unit="kWh" min={0} max={100}
                      value={params.battery_capacity}
                      onChange={(v) => set("battery_capacity", v)} />
        </div>

        <div className="border-t border-slate-100 pt-4">
          <p className="text-sm font-medium text-navy mb-2">Sestava</p>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" name="bom_mode"
                     checked={params.bom_mode === "components"}
                     onChange={() => set("bom_mode", "components")} />
              Jednotlivé komponenty
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="bom_mode"
                     checked={params.bom_mode === "system"}
                     onChange={() => set("bom_mode", "system")} />
              Hotový systém
            </label>
          </div>

          {params.bom_mode === "system" ? (
            <label className="block mt-3">
              <span className="text-sm text-slate-700">Systém</span>
              <select
                value={params.system_material_id ?? ""}
                onChange={(e) => setBomMaterial("system_material_id", e.target.value)}
                className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
              >
                <option value="">— vyberte balíček —</option>
                {systems.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} — {m.name} ({Number(m.price).toLocaleString("cs-CZ")} Kč)
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <MaterialSelect label="Panely" value={params.panel_material_id}
                              options={panels}
                              onChange={(v) => setBomMaterial("panel_material_id", v)} />
              <MaterialSelect label="Měnič" value={params.inverter_material_id}
                              options={inverters}
                              onChange={(v) => setBomMaterial("inverter_material_id", v)} />
              <MaterialSelect label="Baterie" value={params.battery_material_id}
                              options={batteries}
                              onChange={(v) => setBomMaterial("battery_material_id", v)} />
              <MaterialSelect label="Montáž" value={params.install_material_id}
                              options={installs}
                              onChange={(v) => setBomMaterial("install_material_id", v)} />
            </div>
          )}

          <div className="mt-3 text-sm flex justify-between border-t border-slate-100 pt-3">
            <span className="font-medium text-navy">Celková investice</span>
            <span className="font-semibold">{investment.toLocaleString("cs-CZ")} Kč</span>
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4 space-y-4">
          <p className="text-sm font-medium text-navy">Spotřeba a ceny</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <NumberField label="Roční spotřeba" unit="MWh" min={0.1} max={100}
                        value={params.annual_consumption_mwh}
                        onChange={(v) => set("annual_consumption_mwh", v)} />
            <NumberField label="Cena silové energie" unit="Kč/kWh" min={0}
                        value={params.price_power} onChange={(v) => set("price_power", v)} />
            <NumberField label="Cena distribuce" unit="Kč/kWh" min={0}
                        value={params.price_distribution}
                        onChange={(v) => set("price_distribution", v)} />
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4 space-y-4">
          <p className="text-sm font-medium text-navy">Prodej přebytků</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block">
              <span className="text-sm text-slate-700">Schéma prodeje</span>
              <select
                value={params.sell_price_scheme}
                onChange={(e) => set("sell_price_scheme", e.target.value as FveParams["sell_price_scheme"])}
                className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
              >
                {SELL_SCHEMES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>
            {params.sell_price_scheme === "fixed" && (
              <NumberField label="Výkupní cena" unit="Kč/kWh" min={0}
                           value={params.price_sell} onChange={(v) => set("price_sell", v)} />
            )}
            {params.sell_price_scheme === "community" && (
              <NumberField label="Cena komunity" unit="Kč/kWh" min={0}
                           value={params.community_sell_price}
                           onChange={(v) => set("community_sell_price", v)} />
            )}
            {params.sell_price_scheme === "shared" && (
              <NumberField label="Cena sdílení" unit="Kč/kWh" min={0}
                           value={params.shared_sell_price}
                           onChange={(v) => set("shared_sell_price", v)} />
            )}
            {params.sell_price_scheme === "spot" && (
              <NumberField label="Marže nad spotem" unit="Kč/kWh" min={0}
                           value={params.spot_price_margin}
                           onChange={(v) => set("spot_price_margin", v)} />
            )}
          </div>
        </div>
      </Card>

      <Card title="Umístění a pokročilé parametry">
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
          <label className="block text-sm text-slate-700">
            Obec nebo město
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="např. Praha"
              className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
            />
          </label>
          <p className="text-xs text-slate-500 mt-1">
            Vyhledává se obec, ne ulice — zadejte např. „Praha" nebo „Brno".
          </p>
          {geoError && <p className="text-xs text-red-600 mt-1">{geoError}</p>}
          {geo && (
            <p className="text-xs text-emerald-700 mt-1">
              Nalezeno: {geo.display_name} ({geo.latitude.toFixed(4)}, {geo.longitude.toFixed(4)})
            </p>
          )}
          <button
            type="button"
            onClick={doGeocode}
            disabled={geocoding}
            className="mt-2 text-sm text-navy underline disabled:opacity-50"
          >
            {geocoding ? "Hledám…" : "Vyhledat souřadnice"}
          </button>
        </div>

        <button
          type="button"
          onClick={() => setShowAdvanced((s) => !s)}
          className="text-sm text-navy underline"
        >
          {showAdvanced ? "Skrýt pokročilé parametry" : "Pokročilé parametry"}
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <NumberField label="Zeměpisná šířka" min={-90} max={90} step={0.0001}
                         value={params.latitude} onChange={(v) => set("latitude", v)} />
            <NumberField label="Zeměpisná délka" min={-180} max={180} step={0.0001}
                         value={params.longitude} onChange={(v) => set("longitude", v)} />
            <NumberField label="Sklon střešního panelu" unit="°" min={0} max={90} step={1}
                         value={params.surface_tilt} onChange={(v) => set("surface_tilt", v)} />
            <NumberField label="Azimut" unit="°" min={0} max={359} step={1}
                         value={params.surface_azimuth} onChange={(v) => set("surface_azimuth", v)} />
            <NumberField label="Systémové ztráty" unit="%" min={0} max={50}
                         value={params.system_loss_factor}
                         onChange={(v) => set("system_loss_factor", v)} />
            <NumberField label="Zimní ztráty" unit="%" min={0} max={100}
                         value={params.winter_loss_factor}
                         onChange={(v) => set("winter_loss_factor", v)} />
            <NumberField
              label="Limit exportu do sítě"
              unit="kW"
              min={0}
              help="Prázdné = bez limitu"
              value={params.grid_export_limit_kw ?? NaN}
              onChange={(v) => set("grid_export_limit_kw", Number.isNaN(v) ? null : v)}
            />
            <NumberField label="Tepelná baterie" unit="kWh" min={0}
                         value={params.thermal_battery_capacity_kwh}
                         onChange={(v) => set("thermal_battery_capacity_kwh", v)} />
            <NumberField label="Výkon dobíjení tepelné baterie" unit="kW" min={0}
                         value={params.thermal_battery_charge_power_kw}
                         onChange={(v) => set("thermal_battery_charge_power_kw", v)} />
          </div>
        )}
      </Card>

      <Card title={`Spotřebiče v domácnosti (${params.active_appliances.length} zapnuto)`}>
        {appliances.length === 0 ? (
          <p className="text-sm text-slate-500">Načítám katalog spotřebičů…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {appliances.map((a) => (
              <label key={a.name} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={params.active_appliances.includes(a.name)}
                  onChange={(e) => toggleAppliance(a.name, e.target.checked)}
                  className="mt-1"
                />
                <span>
                  {a.name}
                  <span className="block text-xs text-slate-500">
                    {a.power_kw} kW · {a.description}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </Card>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onRun}
          disabled={running}
          className="bg-antelonGreen text-navy font-semibold px-6 py-3 rounded-lg hover:brightness-110 disabled:opacity-50"
        >
          {running ? "Počítám…" : "Spočítat analýzu"}
        </button>
      </div>
    </div>
  );
}