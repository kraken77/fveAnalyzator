import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client from "../api/client";
import { convertToOrder, DEFAULT_FVE_PARAMS, fetchAppliances, runAnalysis } from "../api/fve";
import ContactStep from "../components/fve/ContactStep";
import FveAnalysisForm from "../components/fve/FveAnalysisForm";
import FveAnalysisResults from "../components/fve/FveAnalysisResults";
import { useAuth, hasAnyRole } from "../context/AuthContext";
import type { FveAnalysisResult, FveAppliance, FveParams } from "../types";

type Tab = "form" | "results" | "contact";

interface ProjectInfo {
  id: number;
  name: string;
  status: string;
  customer_name: string | null;
  customer_email: string | null;
  fve_params: Partial<FveParams> | null;
}

export default function ProjectFveAnalysisPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [loadError, setLoadError] = useState("");
  const [params, setParams] = useState<FveParams>(DEFAULT_FVE_PARAMS);
  const [appliances, setAppliances] = useState<FveAppliance[]>([]);
  const [result, setResult] = useState<FveAnalysisResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("form");
  const [converting, setConverting] = useState(false);

  const canConvert = hasAnyRole(user, ["admin", "antelon"]);

  useEffect(() => {
    fetchAppliances().then(setAppliances).catch(() => setAppliances([]));
  }, []);

  useEffect(() => {
    if (!id) return;
    client
      .get<ProjectInfo>(`/projects/${id}`)
      .then((res) => {
        setProject(res.data);
        // {} nebo {} s contact_* znamená „v této zakázce analýza ještě není"
        const saved = res.data.fve_params ?? {};
        setParams({ ...DEFAULT_FVE_PARAMS, ...saved });
      })
      .catch((e) => setLoadError(e?.response?.data?.detail || "Projekt nelze načíst"));
  }, [id]);

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

  const convert = async () => {
    if (!project) return;
    setConverting(true);
    setError("");
    try {
      await client.put(`/projects/${project.id}/params`, { fve_params: params });
      await convertToOrder(project.id);
      navigate(`/projects/${project.id}/pipeline`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Zakázku se nepodařilo vytvořit");
    } finally {
      setConverting(false);
    }
  };

  if (loadError) {
    return (
      <p className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
        {loadError}
      </p>
    );
  }
  if (!project) {
    return <p className="text-sm text-slate-500 py-10">Načítám projekt…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy">fveAnalysis — {project.name}</h1>
        <p className="text-sm text-slate-600 mt-1">
          Analýza navázaná na existující zakázku. Uloží se do parametrů projektu.
        </p>
      </div>

      {project.status !== "fve_analyza" && (
        <p className="bg-amber-50 border border-amber-200 text-amber-900 text-sm rounded-lg p-3">
          Tato zakázka je ve stavu <strong>{project.status}</strong>, ne rozpracovaná
          analýza. Analýza se uloží jako doplněk — nepřepíše stávající parametry zakázky.
        </p>
      )}

      {error && (
        <p className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
          {error}
        </p>
      )}

      <div className="flex gap-2 border-b border-slate-200">
        {([
          ["form", "Parametry"],
          ["results", "Výsledky"],
          ["contact", "Uložit do zakázky"],
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
        <div className="space-y-3">
          <ContactStep params={params} projectId={project.id} />
          {canConvert && project.status === "fve_analyza" && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={convert}
                disabled={converting}
                className="bg-antelonGreen text-navy font-semibold px-5 py-2.5 rounded-lg hover:brightness-110 disabled:opacity-50"
              >
                {converting ? "Vytvářím zakázku…" : "Vytvořit zakázku a pokračovat"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
