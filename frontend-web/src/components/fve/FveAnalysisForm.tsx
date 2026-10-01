import { useState } from "react";
import { geocode } from "../../api/fve";
import type { FveAppliance, FveGeocode, FveParams } from "../../types";

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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
      <h3 className="font-semibold text-navy">{title}</h3>
      {children}
    </section>
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

  const set = <K extends keyof FveParams>(key: K, value: FveParams[K]) =>
    onChange({ ...params, [key]: value });

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

  return (
    <div className="space-y-4">
      <Section title="Fotovoltaická elektrárna">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <NumberField label="Instalovaný výkon" unit="kWp" min={0.1} max={50}
                      value={params.kwp} onChange={(v) => set("kwp", v)} />
          <NumberField label="Kapacita baterie" unit="kWh" min={0} max={100}
                      value={params.battery_capacity}
                      onChange={(v) => set("battery_capacity", v)} />
        </div>
      </Section>

      <Section title="Spotřeba a ceny">
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
      </Section>

      <Section title="Prodej přebytků">
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
      </Section>

      <Section title="Umístění a pokročilé parametry">
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
          {/* Open-Meteo je name search — „adresa" by lalo lidi zbytečně hledat ulici */}
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
      </Section>

      <Section title={`Spotřebiče v domácnosti (${params.active_appliances.length} zapnuto)`}>
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
      </Section>

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
