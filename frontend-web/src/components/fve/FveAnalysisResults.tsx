import PlotlyChart from "./PlotlyChart";
import { downloadEnergyPdf, runEconomic } from "../../api/fve";
import { useState } from "react";
import type { FveAnalysisResult, FveEconomicResult, FveParams } from "../../types";

function Metric({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-navy mt-1">
        {value.toLocaleString("cs-CZ", { maximumFractionDigits: 0 })} {unit}
      </div>
    </div>
  );
}

/** „Základní chod" nahoře, „CELKEM" dole — stejně jako v legacy Streamlitu. */
const APP_SORT = (name: string) =>
  name === "Základní chod" ? 0 : name === "CELKEM" ? 2 : 1;

export default function FveAnalysisResults(
  { result, params }: { result: FveAnalysisResult; params: Partial<FveParams> },
) {
  const [economic, setEconomic] = useState<FveEconomicResult | null>(null);
  const [econLoading, setEconLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [error, setError] = useState("");

  const loadEconomic = async () => {
    setEconLoading(true);
    setError("");
    try {
      setEconomic(await runEconomic({
        ...params,
        annual_savings: result.financial_balance.annual_savings_czk,
      }));
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Ekonomickou analýzu se nepodařilo spočítat");
    } finally {
      setEconLoading(false);
    }
  };

  const downloadPdf = async () => {
    setPdfLoading(true);
    setError("");
    try {
      // PDF má mít ekonomickou sekci — když ještě není spočítaná, dodělej ji.
      let econ = economic;
      if (!econ) {
        econ = await runEconomic({
          ...params,
          annual_savings: result.financial_balance.annual_savings_czk,
        });
        setEconomic(econ);
      }
      const res = await downloadEnergyPdf(result, econ);
      const url = window.URL.createObjectURL(
        new Blob([res.data], { type: "application/pdf" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "Energeticka_analyza.pdf";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "PDF se nepodařilo stáhnout");
    } finally {
      setPdfLoading(false);
    }
  };

  const e = result.energy_balance_kwh;
  const f = result.financial_balance;
  const p = result.production_details;
  const selfSupplyPct = e.total_consumption > 0
    ? (e.self_consumption / e.total_consumption) * 100
    : 0;

  return (
    <div className="space-y-6">
      {error && (
        <p className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
          {error}
        </p>
      )}

      <section>
        <h3 className="font-semibold text-navy mb-3">Přehled</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Metric label="Roční úspora" value={f.annual_savings_czk} unit="Kč" />
          <Metric label="Náklady bez FVE" value={f.cost_without_pv_czk} unit="Kč" />
          <Metric label="Výroba" value={p.total_production_actual} unit="kWh" />
          <Metric label="Vlastní spotřeba" value={e.self_consumption} unit="kWh" />
          <Metric label="Odkup ze sítě" value={e.grid_import} unit="kWh" />
          <Metric label="Prodej do sítě" value={e.grid_export} unit="kWh" />
          <Metric label="Celková spotřeba" value={e.total_consumption} unit="kWh" />
          <Metric label="Výkonnost systému" value={p.production_performance_pct} unit="%" />
        </div>
        <p className="text-sm text-slate-600 mt-3">
          Z vlastní spotřeby pokrývá FVE <strong>{selfSupplyPct.toFixed(1)} %</strong> domácnosti.
        </p>
      </section>

      <section>
        <h3 className="font-semibold text-navy mb-3">Grafy</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PlotlyChart json={result.plots.savings_pie} title="Struktura úspor" />
          <PlotlyChart json={result.plots.energy_pie} title="Složení energie" />
          <PlotlyChart json={result.plots.monthly_stats} title="Měsíční statistiky" />
          <PlotlyChart json={result.plots.savings_treemap} title="Úspory podle spotřebičů" />
          <PlotlyChart json={result.plots.energy_treemap} title="Energie podle spotřebičů" />
        </div>
      </section>

      {Object.keys(result.appliance_metrics).length > 0 && (
        <section>
          <h3 className="font-semibold text-navy mb-3">Spotřebiče</h3>
          <div className="overflow-x-auto bg-white rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">Spotřebič</th>
                  <th className="px-3 py-2 text-right">Z FVE (kWh)</th>
                  <th className="px-3 py-2 text-right">Ze sítě (kWh)</th>
                  <th className="px-3 py-2 text-right">Úspora (Kč)</th>
                  <th className="px-3 py-2 text-right">Pokrytí</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.appliance_metrics)
                  .sort(([a], [b]) => APP_SORT(a) - APP_SORT(b) || a.localeCompare(b, "cs"))
                  .map(([name, m]) => (
                    <tr
                      key={name}
                      className={
                        name === "CELKEM" ? "font-semibold bg-slate-100"
                          : name === "Základní chod" ? "bg-slate-50" : ""
                      }
                    >
                      <td className="px-3 py-2">{name}</td>
                      <td className="px-3 py-2 text-right">{m.fve_kWh.toFixed(0)}</td>
                      <td className="px-3 py-2 text-right">{m.grid_kWh.toFixed(0)}</td>
                      <td className="px-3 py-2 text-right">
                        {m.savings_czk.toLocaleString("cs-CZ")}
                      </td>
                      <td className="px-3 py-2 text-right">{m.coverage_pct.toFixed(1)} %</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section>
        <h3 className="font-semibold text-navy mb-3">Ekonomická analýza</h3>
        {!economic ? (
          <button
            type="button"
            onClick={loadEconomic}
            disabled={econLoading}
            className="text-sm text-navy underline disabled:opacity-50"
          >
            {econLoading ? "Počítám…" : "Spočítat návratnost investice"}
          </button>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              <Metric label="Investice" value={economic.investment_cost} unit="Kč" />
              <Metric label="Návratnost" value={Number(economic.metrics.payback_years)} unit="let" />
              <Metric label="Diskontovaná návratnost"
                      value={Number(economic.metrics.discounted_payback_years)} unit="let" />
              <Metric label="Čistá současná hodnota" value={economic.metrics.npv_czk} unit="Kč" />
              <Metric label="Výnos FVE" value={economic.metrics.final_pv_gain_czk} unit="Kč" />
              <Metric label="Výnos FVE s reinvesticí"
                      value={economic.metrics.final_pv_reinvest_gain_czk} unit="Kč" />
              <Metric label="Výnos S&P500" value={economic.metrics.final_sp500_net_czk} unit="Kč" />
            </div>
            <PlotlyChart json={economic.plot} title="Investice vs S&P500" />
          </div>
        )}
      </section>

      {result.recommendations.length > 0 && (
        <section>
          <h3 className="font-semibold text-navy mb-3">Doporučení</h3>
          <ul className="list-disc list-inside space-y-1 text-sm text-slate-700">
            {result.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex justify-end border-t border-slate-200 pt-4">
        <button
          type="button"
          onClick={downloadPdf}
          disabled={pdfLoading}
          className="border border-navy text-navy px-5 py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          {pdfLoading ? "Generuji…" : "Stáhnout PDF"}
        </button>
      </div>
    </div>
  );
}
