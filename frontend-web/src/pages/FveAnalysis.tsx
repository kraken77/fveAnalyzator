import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchAppliances, runAnalysis } from "../api/fve";
import { DEFAULT_FVE_PARAMS } from "../api/fve";
import ContactStep from "../components/fve/ContactStep";
import FveAnalysisForm from "../components/fve/FveAnalysisForm";
import FveAnalysisResults from "../components/fve/FveAnalysisResults";
import type { FveAnalysisResult, FveAppliance, FveParams } from "../types";

type Tab = "form" | "results" | "contact";

export default function FveAnalysisPage() {
  const navigate = useNavigate();
  const [params, setParams] = useState<FveParams>(DEFAULT_FVE_PARAMS);
  const [appliances, setAppliances] = useState<FveAppliance[]>([]);
  const [result, setResult] = useState<FveAnalysisResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("form");

  useEffect(() => {
    fetchAppliances().then(setAppliances).catch(() => setAppliances([]));
  }, []);

  const run = async () => {
    setRunning(true);
    setError("");
    try {
      setResult(await runAnalysis(params));
      setTab("results");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Analýzu se nepodařilo spočítat");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy">fveAnalysis</h1>
        <p className="text-sm text-slate-600 mt-1">
          Energetická a ekonomická analýza fotovoltaické elektrárny. První krok zakázky —
          výsledky můžete uložit a pokračovat v projektu.
        </p>
      </div>

      {error && (
        <p className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
          {error}
        </p>
      )}

      <div className="flex gap-2 border-b border-slate-200">
        {([
          ["form", "Parametry"],
          ["results", "Výsledky"],
          ["contact", "Kontakt a uložení"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            disabled={key !== "form" && !result}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px disabled:opacity-40 ${
              tab === key
                ? "border-antelonGreen text-navy"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "form" && (
        <FveAnalysisForm
          params={params}
          onChange={setParams}
          appliances={appliances}
          onRun={run}
          running={running}
        />
      )}

      {tab === "results" && result && <FveAnalysisResults result={result} />}

      {tab === "contact" && (
        <ContactStep
          params={params}
          onSaved={(saved) => {
            if (saved) navigate(`/projects/${saved.id}`);
          }}
        />
      )}
    </div>
  );
}
