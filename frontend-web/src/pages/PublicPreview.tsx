import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { publicClient } from "../api/client";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";

interface PublicData {
  project?: {
    id?: string | number;
    name?: string;
    customer_name?: string;
    description?: string;
  };
  name?: string;
  customer_name?: string;
  title?: string;
  kpi?: Record<string, number>;
  phase_pct?: { A?: number; B?: number; C?: number };
  warnings?: string[];
  gaps?: string[];
  sections?: Array<{
    id?: string;
    title?: string;
    visibility?: string;
    content?: string;
  }>;
  pdfs?: Array<{
    id: string | number;
    template?: string;
    version?: string | number;
  }>;
  is_linked?: boolean;
  linked?: boolean;
  [key: string]: unknown;
}

export default function PublicPreview() {
  const { code } = useParams<{ code: string }>();
  const { user, token } = useAuth();
  const [data, setData] = useState<PublicData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [joinMsg, setJoinMsg] = useState<string | null>(null);
  const [joinBusy, setJoinBusy] = useState(false);

  const isLinked =
    (data?.is_linked as boolean) ?? (data?.linked as boolean) ?? !!user; // fallback: if logged and project fetch succeeded without blur concept

  useEffect(() => {
    if (!code) return;
    setLoading(true);
    setError(null);
    // Try unauthenticated first via publicClient; if token exists we also try authenticated fetch via client
    // Prefer publicClient without token for correct teaser behavior; but we need to know linked state, so if logged, fetch with auth as second try
    const fetchPublic = async () => {
      try {
        // try public endpoint without auth
        const res = await publicClient.get(`/public/p/${code}`);
        setData(res.data as PublicData);
      } catch (e: unknown) {
        // if 401/404 try with auth if token exists
        if (token) {
          try {
            const res2 = await client.get(`/public/p/${code}`);
            setData(res2.data as PublicData);
            return;
          } catch (inner: unknown) {
            const m =
              (inner as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
              (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
              "Projekt nenalezen";
            setError(m);
            return;
          }
        }
        const m =
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (e instanceof Error ? e.message : "Chyba načtení");
        setError(m);
      } finally {
        setLoading(false);
      }
    };
    fetchPublic();
  }, [code, token]);

  const handleJoin = async () => {
    if (!code) return;
    if (!token) {
      setJoinMsg("Nejdříve se přihlaste nebo zaregistrujte.");
      return;
    }
    setJoinBusy(true);
    setJoinMsg(null);
    try {
      await client.post(`/public/join`, { code });
      setJoinMsg("Úspěšně připojeno! Nyní vidíte plný náhled.");
      // refetch with auth
      const res = await client.get(`/public/p/${code}`);
      setData(res.data as PublicData);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Připojení selhalo";
      setJoinMsg(m);
    } finally {
      setJoinBusy(false);
    }
  };

  const handleDownload = async (pdfId: string | number) => {
    // attempt anonymous download via publicClient if project id known, else client
    // data may contain project.id and pdfs
    const pid = (data?.project?.id as string | number | undefined) ?? (data as { project_id?: string | number })?.project_id;
    if (!pid) {
      alert("Nelze stáhnout — chybí ID projektu");
      return;
    }
    try {
      // try public download without auth (watermarked for anonymous)
      const url = `/projects/${pid}/pdfs/${pdfId}/download`;
      // choose client depending on auth; for anonymous we want publicClient
      const chosen = token ? client : publicClient;
      const res = await chosen.get(url, { responseType: "blob" });
      const blob = new Blob([res.data as BlobPart], { type: "application/pdf" });
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = `report-${pdfId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch {
      alert("Stažení selhalo");
    }
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-sm text-slateMuted animate-pulse">Načítám náhled...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center p-4">
        <div className="card p-8 max-w-md w-full text-center border-l-4 border-l-red-400">
          <p className="font-semibold text-navy">Náhled nenalezen</p>
          <p className="text-sm text-slateMuted mt-1">{error}</p>
          <p className="text-xs text-slateMuted mt-2">Kód: {code}</p>
          <Link to="/login" className="btn-primary mt-4 inline-block text-sm">
            Přihlásit se
          </Link>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const projectName =
    (data.project?.name as string) ?? (data.name as string) ?? (data.title as string) ?? "Projekt";
  const customer = (data.project?.customer_name as string) ?? (data.customer_name as string) ?? "";
  const kpi = (data.kpi as Record<string, number> | undefined) ?? (data as Record<string, number>);
  const avgDaily = (kpi?.avg_daily_kwh as number | undefined) ?? (data as { avg_daily_kwh?: number }).avg_daily_kwh;
  const totalKwh = (kpi?.total_kwh as number | undefined) ?? (data as { total_kwh?: number }).total_kwh;
  const annualMwh = (kpi?.annual_mwh as number | undefined) ?? (data as { annual_mwh?: number }).annual_mwh;
  const nComplete = (kpi?.n_complete as number | undefined) ?? (data as { n_complete?: number }).n_complete;
  const phasePct = (data.phase_pct as { A?: number; B?: number; C?: number } | undefined) ?? {};
  const sections = (data.sections as Array<{ id?: string; title?: string; visibility?: string; content?: string }> | undefined) ?? [];

  // fallback sections if not provided
  const fallbackSections =
    sections.length === 0
      ? [
          { id: "summary", title: "Shrnutí KPI", visibility: "full", content: "Celková spotřeba, průměry, odhad ročně." },
          { id: "battery", title: "Simulace baterie", visibility: "teaser", content: "15 / 20 kWh, SoC 30 %, nabíjení z přebytku." },
          { id: "variants", title: "Varianty FVE", visibility: "teaser", content: "20 / 25 / 30 kWp — roční výroba a pokrytí." },
          { id: "recommendation", title: "Doporučení", visibility: "internal", content: "FVE 25 kWp + baterie 15–20 kWh — detailní zdůvodnění." },
        ]
      : sections;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* navy header */}
      <header className="bg-navy text-white">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-antelonGreen flex items-center justify-center font-black text-navy">A</div>
            <span className="font-bold tracking-wide text-sm">ANTELON ENERGY s.r.o.</span>
          </div>
          <div className="flex items-center gap-2">
            {!token ? (
              <>
                <Link to="/login" className="text-sm bg-white/10 px-3 py-1.5 rounded hover:bg-white/20">
                  Přihlášení
                </Link>
                <Link to="/register" className="text-sm bg-antelonGreen text-navy font-semibold px-3 py-1.5 rounded">
                  Registrace
                </Link>
              </>
            ) : (
              <span className="text-xs bg-white/10 px-3 py-1.5 rounded">{user?.email}</span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6">
        {/* title */}
        <div className="card p-6 border-l-4 border-l-antelonGreen">
          <p className="text-xs font-semibold tracking-widest text-slateMuted uppercase">Veřejný náhled</p>
          <h1 className="text-2xl font-bold text-navy mt-1">{projectName}</h1>
          {customer && <p className="text-sm text-slateMuted">{customer}</p>}
          <p className="text-xs text-slateMuted mt-2">
            Kód: <span className="font-mono font-semibold text-navy">{code}</span>
            {isLinked && <span className="ml-2 bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded text-xs">připojen</span>}
            {!isLinked && <span className="ml-2 bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-xs">teaser</span>}
          </p>
        </div>

        {/* KPI — full for linked, still visible for anonymous but maybe limited */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="kpi-card border-l-antelonGreen">
            <p className="text-xs text-slateMuted uppercase">Ø denně</p>
            <p className="text-xl font-bold text-navy mt-1">{avgDaily !== undefined ? `${Number(avgDaily).toFixed(1)} kWh` : "—"}</p>
            <p className="text-xs text-slateMuted">{nComplete !== undefined ? `${nComplete} dní` : ""} {totalKwh !== undefined ? `• ${Number(totalKwh).toFixed(0)} kWh` : ""}</p>
          </div>
          <div className="kpi-card border-l-navy">
            <p className="text-xs text-slateMuted uppercase">Ročně</p>
            <p className="text-xl font-bold text-navy mt-1">{annualMwh !== undefined ? `${Number(annualMwh).toFixed(1)} MWh` : "—"}</p>
          </div>
          <div className="kpi-card border-l-antelonOrange">
            <p className="text-xs text-slateMuted uppercase">Fáze</p>
            <p className="text-sm font-bold text-navy mt-1">
              {phasePct.A !== undefined ? `${Number(phasePct.A).toFixed(0)}%` : "—"} / {phasePct.B !== undefined ? `${Number(phasePct.B).toFixed(0)}%` : "—"} / {phasePct.C !== undefined ? `${Number(phasePct.C).toFixed(0)}%` : "—"}
            </p>
          </div>
          <div className="kpi-card border-l-slateMuted">
            <p className="text-xs text-slateMuted uppercase">Přístup</p>
            <p className="text-sm font-bold text-navy mt-1">{isLinked ? "Plný náhled" : "Teaser (blur)"}</p>
          </div>
        </div>

        {/* warnings/gaps if any and linked or teaser allows */}
        {((data.warnings as string[] | undefined)?.length ?? 0) > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
            {(data.warnings as string[]).join(" • ")}
          </div>
        )}

        {/* CTA */}
        {!isLinked && (
          <div className="card p-5 border-l-4 border-l-antelonOrange bg-gradient-to-r from-white to-amber-50">
            <h3 className="font-semibold text-navy">Chcete plný report bez rozostření a čisté PDF?</h3>
            <p className="text-sm text-slateMuted mt-1">Zaregistrujte se nebo se přihlaste a klikněte na „Připojit se k projektu“.</p>
            <div className="flex flex-wrap gap-2 mt-3">
              {!token ? (
                <>
                  <Link to="/register" className="btn-primary text-sm">
                    Vytvořit účet
                  </Link>
                  <Link to="/login" className="btn-secondary text-sm">
                    Přihlásit se
                  </Link>
                </>
              ) : (
                <button onClick={handleJoin} disabled={joinBusy} className="btn-primary text-sm disabled:opacity-60">
                  {joinBusy ? "Připojuji..." : "Připojit se k projektu"}
                </button>
              )}
            </div>
            {joinMsg && <p className="text-sm text-navy mt-2 bg-white border rounded px-3 py-2">{joinMsg}</p>}
          </div>
        )}
        {isLinked && joinMsg && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm px-3 py-2 rounded">{joinMsg}</div>
        )}

        {/* sections with blur logic */}
        <div className="space-y-4">
          <h2 className="font-bold text-navy">Obsah reportu</h2>
          {fallbackSections.map((sec, idx) => {
            const vis = (sec.visibility as string) ?? "full";
            const shouldBlur = !isLinked && (vis === "teaser" || vis === "internal");
            return (
              <div key={sec.id || String(idx)} className="card p-5 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-navy">{sec.title || `Sekce ${idx + 1}`}</h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium ${
                      vis === "full"
                        ? "bg-emerald-100 text-emerald-700"
                        : vis === "teaser"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-slate-100 text-slateMuted"
                    }`}
                  >
                    {vis}
                  </span>
                </div>
                <div className={`mt-3 text-sm text-slate-700 ${shouldBlur ? "blur-teaser" : ""}`}>
                  <p>{sec.content || "Obsah sekce — grafy, tabulky a doporučení."}</p>
                  {/* mock chart placeholder */}
                  <div className="mt-3 h-24 bg-slate-50 border border-dashed rounded flex items-center justify-center text-xs text-slateMuted">
                    Graf — {sec.title}
                  </div>
                </div>
                {shouldBlur && (
                  <div className="absolute inset-0 flex items-center justify-center bg-white/40 backdrop-blur-[1px]">
                    <span className="bg-navy text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow">
                      🔒 Zpracováno — dostupné po připojení
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* pdfs */}
        {data.pdfs && data.pdfs.length > 0 && (
          <div className="card p-5">
            <h3 className="font-semibold text-navy">PDF ke stažení</h3>
            <p className="text-xs text-slateMuted">
              {isLinked ? "Čisté PDF bez vodotisku." : "Anonymní stažení obsahuje vodotisk NÁVRH — KONFIDENCIÁLNÍ."}
            </p>
            <div className="divide-y mt-3">
              {(data.pdfs as Array<{ id: string | number; template?: string; version?: string | number }>).map((pdf) => (
                <div key={String(pdf.id)} className="flex items-center justify-between py-2.5">
                  <span className="text-sm font-medium text-navy">
                    {pdf.template || "report"} v{String(pdf.version ?? "")}
                  </span>
                  <button onClick={() => handleDownload(pdf.id)} className="btn-secondary text-xs">
                    Stáhnout PDF
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="text-center text-xs text-slateMuted pt-4">
          <Link to="/projects" className="hover:text-navy">
            ← Zpět na přehled projektů
          </Link>
        </div>
      </main>
    </div>
  );
}
