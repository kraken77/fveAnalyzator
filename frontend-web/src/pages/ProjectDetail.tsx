import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import client from "../api/client";

// Types
interface Project {
  id: string | number;
  name: string;
  customer_name?: string;
  description?: string;
  share_code?: string;
  antelon_params?: Record<string, unknown>;
  fve_params?: Record<string, unknown>;
  created_at?: string;
}

interface FileItem {
  id: string | number;
  filename: string;
  kind?: string;
  path?: string;
  uploaded_at?: string;
}

interface DataPreview {
  kpi?: {
    n_complete?: number;
    total_kwh?: number;
    avg_daily_kwh?: number;
    annual_mwh?: number;
    weekday_avg?: number;
    weekend_avg?: number;
  };
  kpi2?: Record<string, number>;
  phase_pct?: { A?: number; B?: number; C?: number };
  green_kwh?: number;
  red_kwh?: number;
  warnings?: string[];
  gaps?: string[];
  daily?: Array<Record<string, unknown>>;
  complete_days?: string[];
  n_complete?: number;
  total_kwh?: number;
  avg_daily_kwh?: number;
  [key: string]: unknown;
}

interface Photo {
  id: string | number;
  filename: string;
  caption?: string;
  path?: string;
  url?: string;
}

interface PdfVersion {
  id: string | number;
  template: string;
  version: number | string;
  audience?: string;
  created_at?: string;
  file_path?: string;
}

type TabId = "data" | "params" | "preview" | "pdf" | "photos" | "share";

const TABS: { id: TabId; label: string }[] = [
  { id: "data", label: "Data" },
  { id: "params", label: "Parametry" },
  { id: "preview", label: "Náhled" },
  { id: "pdf", label: "PDF" },
  { id: "photos", label: "Fotky" },
  { id: "share", label: "Sdílení" },
];

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const [active, setActive] = useState<TabId>("data");

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [files, setFiles] = useState<FileItem[]>([]);
  const [dataPreview, setDataPreview] = useState<DataPreview | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [pdfs, setPdfs] = useState<PdfVersion[]>([]);
  const [share, setShare] = useState<{ code?: string; url?: string; qr_b64?: string } | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // drag & drop
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // params form
  const [projForm, setProjForm] = useState({ name: "", customer_name: "", description: "" });
  const [antelonForm, setAntelonForm] = useState<Record<string, string>>({
    kwp: "25",
    battery_kwh: "20",
    soc_min: "30",
    title: "",
    subtitle: "",
    // texts for sections (store as simple keys)
    section_summary_text: "",
    section_battery_text: "",
  });
  const [fveForm, setFveForm] = useState<Record<string, string>>({
    kwp: "25",
    battery_kwh: "15",
    annual_consumption_mwh: "21.4",
    price_buy: "6.5",
    price_sell: "2.5",
    lat: "49.8",
    lon: "18.3",
  });
  const [visibility, setVisibility] = useState<Record<string, string>>({
    summary: "full",
    battery: "full",
    variants: "teaser",
  });

  const fetchAll = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await client.get(`/projects/${id}`);
      const p = (res.data as { project?: Project } & Project)?.project ?? (res.data as Project);
      setProject(p);
      setProjForm({
        name: p.name || "",
        customer_name: p.customer_name || "",
        description: p.description || "",
      });
      if (p.antelon_params) {
        const ap = p.antelon_params as Record<string, unknown>;
        setAntelonForm((prev) => ({
          ...prev,
          kwp: String((ap.kwp as string | number) ?? ap.kWp ?? prev.kwp),
          battery_kwh: String((ap.battery_kwh as string | number) ?? prev.battery_kwh),
          soc_min: String((ap.soc_min as string | number) ?? prev.soc_min),
          title: (ap.title as string) ?? prev.title,
          subtitle: (ap.subtitle as string) ?? prev.subtitle,
        }));
        if (ap.visibility && typeof ap.visibility === "object") {
          setVisibility((prev) => ({ ...prev, ...(ap.visibility as Record<string, string>) }));
        }
      }
      if (p.fve_params) {
        const fp = p.fve_params as Record<string, unknown>;
        setFveForm((prev) => ({
          ...prev,
          kwp: String((fp.kwp as string | number) ?? prev.kwp),
          battery_kwh: String((fp.battery_kwh as string | number) ?? fp.battery ?? prev.battery_kwh),
          annual_consumption_mwh: String(
            (fp.annual_consumption_mwh as string | number) ??
              (fp.annual_consumption as string | number) ??
              prev.annual_consumption_mwh,
          ),
          price_buy: String((fp.price_buy as string | number) ?? prev.price_buy),
          price_sell: String((fp.price_sell as string | number) ?? prev.price_sell),
          lat: String((fp.lat as string | number) ?? prev.lat),
          lon: String((fp.lon as string | number) ?? prev.lon),
        }));
      }
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : "Chyba načtení projektu");
      setError(m);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const fetchFiles = useCallback(async () => {
    if (!id) return;
    try {
      const res = await client.get(`/projects/${id}/files`);
      const data = res.data as unknown;
      const list: FileItem[] = Array.isArray(data)
        ? (data as FileItem[])
        : ((data as { files?: FileItem[] })?.files ?? []);
      setFiles(list);
    } catch {
      // ignore
    }
  }, [id]);

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      const res = await client.get(`/projects/${id}/data`);
      setDataPreview(res.data as DataPreview);
    } catch {
      // no data yet
    }
  }, [id]);

  const fetchPhotos = useCallback(async () => {
    if (!id) return;
    try {
      const res = await client.get(`/projects/${id}/photos`);
      const data = res.data as unknown;
      const list: Photo[] = Array.isArray(data)
        ? (data as Photo[])
        : ((data as { photos?: Photo[] })?.photos ?? []);
      setPhotos(list);
    } catch {
      // ignore
    }
  }, [id]);

  const fetchPdfs = useCallback(async () => {
    if (!id) return;
    try {
      const res = await client.get(`/projects/${id}/pdfs`);
      const data = res.data as unknown;
      const list: PdfVersion[] = Array.isArray(data)
        ? (data as PdfVersion[])
        : ((data as { pdfs?: PdfVersion[] })?.pdfs ??
          (data as { versions?: PdfVersion[] })?.versions ??
          []);
      setPdfs(list);
    } catch {
      // ignore
    }
  }, [id]);

  const fetchShare = useCallback(async () => {
    if (!id) return;
    try {
      // try GET share info if exists, else POST will create
      // spec says POST /projects/{id}/share returns code/url/qr
      // we try GET first via project share_code
      if (project?.share_code) {
        setShare({
          code: project.share_code,
          url: `${window.location.origin}/p/${project.share_code}`,
          qr_b64: undefined,
        });
      }
    } catch {
      // ignore
    }
  }, [id, project?.share_code]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    fetchFiles();
    fetchData();
    fetchPhotos();
    fetchPdfs();
    fetchShare();
  }, [fetchFiles, fetchData, fetchPhotos, fetchPdfs, fetchShare]);

  // reload data when tab changes
  useEffect(() => {
    if (active === "data") {
      fetchFiles();
      fetchData();
    }
    if (active === "pdf") fetchPdfs();
    if (active === "photos") fetchPhotos();
  }, [active, fetchFiles, fetchData, fetchPdfs, fetchPhotos]);

  const uploadFiles = async (fileList: FileList | File[]) => {
    if (!id || !fileList.length) return;
    setBusy("upload");
    setMsg(null);
    try {
      const fd = new FormData();
      Array.from(fileList).forEach((f) => fd.append("files", f));
      // some backends expect field "file" singular; try "files" first
      await client.post(`/projects/${id}/files`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg(`Nahráno ${fileList.length} souborů`);
      await fetchFiles();
      await fetchData();
    } catch (e: unknown) {
      // try alternative field name 'file'
      try {
        const fd2 = new FormData();
        Array.from(fileList).forEach((f) => fd2.append("file", f));
        await client.post(`/projects/${id}/files`, fd2, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setMsg(`Nahráno ${fileList.length} souborů`);
        await fetchFiles();
        await fetchData();
      } catch (inner: unknown) {
        const m =
          (inner as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "Upload selhal";
        setMsg(m);
      }
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteFile = async (fid: string | number) => {
    if (!id) return;
    if (!confirm("Smazat soubor?")) return;
    try {
      await client.delete(`/projects/${id}/files/${fid}`);
      await fetchFiles();
      await fetchData();
    } catch {
      alert("Mazání selhalo");
    }
  };

  const handleSaveProject = async () => {
    if (!id) return;
    setBusy("saveProj");
    try {
      await client.put(`/projects/${id}`, {
        name: projForm.name,
        customer_name: projForm.customer_name,
        description: projForm.description,
      });
      setMsg("Projekt uložen");
      await fetchAll();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Uložení selhalo";
      setMsg(m);
    } finally {
      setBusy(null);
    }
  };

  const handleSaveParams = async () => {
    if (!id) return;
    setBusy("saveParams");
    try {
      await client.put(`/projects/${id}/params`, {
        antelon_params: {
          kwp: Number(antelonForm.kwp) || 25,
          battery_kwh: Number(antelonForm.battery_kwh) || 20,
          soc_min: Number(antelonForm.soc_min) || 30,
          title: antelonForm.title,
          subtitle: antelonForm.subtitle,
          texts: {
            summary: antelonForm.section_summary_text,
            battery: antelonForm.section_battery_text,
          },
          visibility,
        },
        fve_params: {
          kwp: Number(fveForm.kwp) || 25,
          battery_kwh: Number(fveForm.battery_kwh) || 15,
          annual_consumption_mwh: Number(fveForm.annual_consumption_mwh) || 21.4,
          price_buy: Number(fveForm.price_buy) || 6.5,
          price_sell: Number(fveForm.price_sell) || 2.5,
          lat: Number(fveForm.lat) || 49.8,
          lon: Number(fveForm.lon) || 18.3,
        },
      });
      setMsg("Parametry uloženy");
      await fetchAll();
      await fetchData();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Uložení parametrů selhalo";
      setMsg(m);
    } finally {
      setBusy(null);
    }
  };

  const handleGenerate = async (template: string) => {
    if (!id) return;
    setBusy(`gen-${template}`);
    try {
      await client.post(`/projects/${id}/generate`, { template });
      setMsg(`PDF ${template} vygenerován`);
      await fetchPdfs();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Generování selhalo";
      setMsg(m);
    } finally {
      setBusy(null);
    }
  };

  const handleDownload = async (pdfId: string | number) => {
    if (!id) return;
    try {
      const res = await client.get(`/projects/${id}/pdfs/${pdfId}/download`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data as BlobPart], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report-${pdfId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      alert("Stažení selhalo");
    }
  };

  const [photoCaption, setPhotoCaption] = useState("");
  const photoInputRef = useRef<HTMLInputElement>(null);

  const handlePhotoUpload = async (filesList: FileList | null) => {
    if (!id || !filesList || !filesList.length) return;
    setBusy("photo");
    try {
      const fd = new FormData();
      fd.append("file", filesList[0]);
      if (photoCaption) fd.append("caption", photoCaption);
      // try alternative field "photo"
      await client
        .post(`/projects/${id}/photos`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .catch(async () => {
          const fd2 = new FormData();
          fd2.append("photo", filesList[0]);
          if (photoCaption) fd2.append("caption", photoCaption);
          await client.post(`/projects/${id}/photos`, fd2, {
            headers: { "Content-Type": "multipart/form-data" },
          });
        });
      setPhotoCaption("");
      if (photoInputRef.current) photoInputRef.current.value = "";
      await fetchPhotos();
      setMsg("Foto nahráno");
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Nahrání fotky selhalo";
      setMsg(m);
    } finally {
      setBusy(null);
    }
  };

  const handleCreateShare = async () => {
    if (!id) return;
    setBusy("share");
    try {
      const res = await client.post(`/projects/${id}/share`);
      const data = res.data as { code?: string; url?: string; qr_b64?: string; qr?: string };
      setShare({
        code: data.code,
        url: data.url,
        qr_b64: data.qr_b64 || data.qr,
      });
      setMsg("Sdílení vytvořeno");
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Vytvoření sdílení selhalo";
      setMsg(m);
    } finally {
      setBusy(null);
    }
  };

  const handleJoin = async () => {
    if (!share?.code) return;
    setBusy("join");
    try {
      await client.post(`/public/join`, { code: share.code });
      setMsg("Úspěšně připojeno k projektu");
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Připojení selhalo";
      setMsg(m);
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 bg-slate-200 rounded w-1/3" />
        <div className="h-32 bg-slate-200 rounded" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-8 text-center border-l-4 border-l-red-400">
        <p className="text-red-700">{error}</p>
        <Link to="/projects" className="btn-secondary mt-4 inline-block">
          Zpět na projekty
        </Link>
      </div>
    );
  }

  if (!project) return null;

  const kpi = (dataPreview?.kpi as Record<string, number> | undefined) || (dataPreview as Record<string, number> | null) || {};
  const n_complete = (kpi.n_complete ?? dataPreview?.n_complete ?? dataPreview?.kpi?.n_complete) as number | undefined;
  const total_kwh = (kpi.total_kwh ?? dataPreview?.total_kwh ?? dataPreview?.kpi?.total_kwh) as number | undefined;
  const avg_daily = (kpi.avg_daily_kwh ?? dataPreview?.avg_daily_kwh ?? dataPreview?.kpi?.avg_daily_kwh) as number | undefined;
  const annual_mwh = (kpi.annual_mwh ?? dataPreview?.kpi?.annual_mwh) as number | undefined;
  const weekday_avg = (kpi.weekday_avg ?? dataPreview?.kpi?.weekday_avg) as number | undefined;
  const weekend_avg = (kpi.weekend_avg ?? dataPreview?.kpi?.weekend_avg) as number | undefined;
  const phasePct = (dataPreview?.phase_pct as { A?: number; B?: number; C?: number } | undefined) ?? {};
  const warnings = (dataPreview?.warnings as string[] | undefined) ?? [];
  const gaps = (dataPreview?.gaps as string[] | undefined) ?? [];

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <Link to="/projects" className="text-xs text-slateMuted hover:text-navy">
            ← Zpět na projekty
          </Link>
          <h1 className="text-2xl font-bold text-navy mt-1">{project.name}</h1>
          {project.customer_name && (
            <p className="text-sm text-slateMuted">{project.customer_name}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {project.share_code && (
            <span className="text-xs font-mono bg-navy text-white px-2.5 py-1 rounded">
              {project.share_code}
            </span>
          )}
          <span className="text-xs bg-white border px-2 py-1 rounded">
            ID: {String(project.id)}
          </span>
        </div>
      </div>

      {msg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm px-3 py-2 rounded flex justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold ml-4">
            ×
          </button>
        </div>
      )}

      {/* tabs */}
      <div className="border-b border-slate-200 overflow-x-auto">
        <div className="flex gap-1 sm:gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActive(t.id)}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                active === t.id
                  ? "border-antelonGreen text-navy"
                  : "border-transparent text-slateMuted hover:text-navy hover:border-slate-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Data tab */}
      {active === "data" && (
        <div className="space-y-6">
          {/* upload */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              uploadFiles(e.dataTransfer.files);
            }}
            className={`card p-6 border-2 border-dashed transition ${dragOver ? "border-antelonGreen bg-emerald-50" : "border-slate-200 bg-white"}`}
          >
            <div className="text-center">
              <p className="font-medium text-navy">Přetáhněte CSV soubory sem</p>
              <p className="text-xs text-slateMuted mt-1">
                Podporováno: denní spotřeba (Wh), napětí (V), profil 15min — více souborů = sloučení
              </p>
              <div className="mt-4 flex justify-center gap-2">
                <button onClick={() => fileInputRef.current?.click()} className="btn-primary text-sm">
                  Vybrat soubory
                </button>
                <span className="text-xs text-slate-400 self-center">
                  {busy === "upload" ? "Nahrávám..." : "nebo přetáhněte"}
                </span>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".csv,.txt"
                className="hidden"
                onChange={(e) => e.target.files && uploadFiles(e.target.files)}
              />
            </div>
          </div>

          {/* files list */}
          <div className="card p-5">
            <h3 className="font-semibold text-navy mb-3">Nahrané soubory ({files.length})</h3>
            {files.length === 0 ? (
              <p className="text-sm text-slateMuted">Zatím žádné soubory.</p>
            ) : (
              <div className="divide-y">
                {files.map((f) => (
                  <div key={String(f.id)} className="flex items-center justify-between py-2.5">
                    <div>
                      <p className="text-sm font-medium text-navy">{f.filename}</p>
                      <p className="text-xs text-slateMuted">
                        {f.kind || "consumption_daily"} {f.uploaded_at ? `• ${new Date(f.uploaded_at).toLocaleString("cs-CZ")}` : ""}
                      </p>
                    </div>
                    <button
                      onClick={() => handleDeleteFile(f.id)}
                      className="text-xs text-red-600 hover:underline border border-red-200 px-2 py-1 rounded bg-red-50"
                    >
                      Smazat
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* data preview */}
          <div className="card p-5">
            <h3 className="font-semibold text-navy mb-4">Přehled dat</h3>
            {!dataPreview ? (
              <p className="text-sm text-slateMuted">Žádná data k zobrazení — nahrajte CSV.</p>
            ) : (
              <>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                  <div className="kpi-card border-l-antelonGreen">
                    <p className="text-xs text-slateMuted uppercase tracking-wide">Kompletní dny</p>
                    <p className="text-xl font-bold text-navy mt-1">{n_complete ?? "—"}</p>
                  </div>
                  <div className="kpi-card border-l-antelonGreen">
                    <p className="text-xs text-slateMuted uppercase tracking-wide">Celkem</p>
                    <p className="text-xl font-bold text-navy mt-1">
                      {total_kwh !== undefined ? `${Number(total_kwh).toFixed(1)} kWh` : "—"}
                    </p>
                  </div>
                  <div className="kpi-card border-l-antelonGreen">
                    <p className="text-xs text-slateMuted uppercase tracking-wide">Průměr / den</p>
                    <p className="text-xl font-bold text-navy mt-1">
                      {avg_daily !== undefined ? `${Number(avg_daily).toFixed(1)} kWh` : "—"}
                    </p>
                  </div>
                  <div className="kpi-card border-l-antelonOrange">
                    <p className="text-xs text-slateMuted uppercase tracking-wide">Ročně odhad</p>
                    <p className="text-xl font-bold text-navy mt-1">
                      {annual_mwh !== undefined ? `${Number(annual_mwh).toFixed(1)} MWh` : "—"}
                    </p>
                  </div>
                </div>

                {(weekday_avg !== undefined || weekend_avg !== undefined) && (
                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div className="bg-slate-50 rounded-lg p-3 border">
                      <p className="text-xs text-slateMuted">Pracovní den Ø</p>
                      <p className="font-bold text-navy">{weekday_avg !== undefined ? `${Number(weekday_avg).toFixed(1)} kWh` : "—"}</p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-3 border">
                      <p className="text-xs text-slateMuted">Víkend Ø</p>
                      <p className="font-bold text-navy">{weekend_avg !== undefined ? `${Number(weekend_avg).toFixed(1)} kWh` : "—"}</p>
                    </div>
                  </div>
                )}

                {warnings.length > 0 && (
                  <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <p className="text-xs font-semibold text-amber-800">Upozornění</p>
                    <ul className="text-xs text-amber-700 list-disc pl-4 mt-1 space-y-0.5">
                      {warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {gaps.length > 0 && (
                  <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3">
                    <p className="text-xs font-semibold text-red-800">Mezery v měření</p>
                    <p className="text-xs text-red-700 mt-1">{gaps.join(", ")}</p>
                  </div>
                )}

                {Array.isArray(dataPreview.daily) && dataPreview.daily.length > 0 && (
                  <div className="mt-6 overflow-auto max-h-[360px] border rounded-lg">
                    <table className="w-full text-xs sm:text-sm">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          {Object.keys(dataPreview.daily[0] as object).map((k) => (
                            <th key={k} className="px-3 py-2 text-left font-semibold text-slateMuted whitespace-nowrap">
                              {k}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(dataPreview.daily as Array<Record<string, unknown>>).slice(0, 100).map((row, idx) => (
                          <tr key={idx} className="border-t odd:bg-white even:bg-slate-50">
                            {Object.values(row).map((v, j) => (
                              <td key={j} className="px-3 py-1.5 whitespace-nowrap">
                                {String(v ?? "")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {(dataPreview.daily.length as number) > 100 && (
                      <p className="text-xs text-slateMuted p-2 text-center">
                        Zobrazeno prvních 100 z {dataPreview.daily.length} řádků
                      </p>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Params tab */}
      {active === "params" && (
        <div className="space-y-6">
          <div className="card p-5 sm:p-6 border-l-4 border-l-antelonGreen">
            <h3 className="font-semibold text-navy mb-4">Projekt</h3>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-navy">Název</label>
                <input
                  value={projForm.name}
                  onChange={(e) => setProjForm((s) => ({ ...s, name: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Zákazník</label>
                <input
                  value={projForm.customer_name}
                  onChange={(e) => setProjForm((s) => ({ ...s, customer_name: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
                />
              </div>
            </div>
            <div className="mt-4">
              <label className="text-sm font-medium text-navy">Popis</label>
              <textarea
                value={projForm.description}
                onChange={(e) => setProjForm((s) => ({ ...s, description: e.target.value }))}
                rows={2}
                className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
              />
            </div>
            <button
              onClick={handleSaveProject}
              disabled={busy === "saveProj"}
              className="btn-navy mt-4 text-sm disabled:opacity-60"
            >
              {busy === "saveProj" ? "Ukládám..." : "Uložit projekt"}
            </button>
          </div>

          <div className="card p-5 sm:p-6 border-l-4 border-l-navy">
            <h3 className="font-semibold text-navy mb-4">Antelon parametry</h3>
            <div className="grid sm:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-navy">FVE kWp</label>
                <input
                  type="number"
                  value={antelonForm.kwp}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, kwp: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Baterie kWh</label>
                <input
                  type="number"
                  value={antelonForm.battery_kwh}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, battery_kwh: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">SoC min %</label>
                <input
                  type="number"
                  value={antelonForm.soc_min}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, soc_min: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4 mt-4">
              <div>
                <label className="text-sm font-medium text-navy">Titulek reportu</label>
                <input
                  value={antelonForm.title}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, title: e.target.value }))}
                  placeholder="Návrh FVE — Pentagon"
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Podtitulek</label>
                <input
                  value={antelonForm.subtitle}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, subtitle: e.target.value }))}
                  placeholder="Doplnění spotřeba / výroba / baterie"
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="text-sm font-medium text-navy">Text sekce — Summary</label>
                <textarea
                  value={antelonForm.section_summary_text}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, section_summary_text: e.target.value }))}
                  rows={2}
                  placeholder="Volitelný text; lze použít {avg_daily_kwh} apod."
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Text sekce — Baterie</label>
                <textarea
                  value={antelonForm.section_battery_text}
                  onChange={(e) => setAntelonForm((s) => ({ ...s, section_battery_text: e.target.value }))}
                  rows={2}
                  placeholder="Volitelný text"
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="mt-4">
              <p className="text-sm font-medium text-navy mb-2">Viditelnost sekcí</p>
              <div className="grid sm:grid-cols-3 gap-3">
                {Object.entries(visibility).map(([key, val]) => (
                  <div key={key}>
                    <label className="text-xs text-slateMuted">{key}</label>
                    <select
                      value={val}
                      onChange={(e) => setVisibility((v) => ({ ...v, [key]: e.target.value }))}
                      className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm"
                    >
                      <option value="full">full — všichni</option>
                      <option value="teaser">teaser — blur pro anonymous</option>
                      <option value="internal">internal — jen antelon/admin</option>
                    </select>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card p-5 sm:p-6 border-l-4 border-l-antelonOrange">
            <h3 className="font-semibold text-navy mb-4">FVE parametry (wrap)</h3>
            <div className="grid sm:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-navy">kWp</label>
                <input
                  type="number"
                  value={fveForm.kwp}
                  onChange={(e) => setFveForm((s) => ({ ...s, kwp: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Baterie kWh</label>
                <input
                  type="number"
                  value={fveForm.battery_kwh}
                  onChange={(e) => setFveForm((s) => ({ ...s, battery_kwh: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Roční spotřeba MWh</label>
                <input
                  type="number"
                  step="0.1"
                  value={fveForm.annual_consumption_mwh}
                  onChange={(e) => setFveForm((s) => ({ ...s, annual_consumption_mwh: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Cena nákup Kč/kWh</label>
                <input
                  type="number"
                  step="0.1"
                  value={fveForm.price_buy}
                  onChange={(e) => setFveForm((s) => ({ ...s, price_buy: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-navy">Cena prodej Kč/kWh</label>
                <input
                  type="number"
                  step="0.1"
                  value={fveForm.price_sell}
                  onChange={(e) => setFveForm((s) => ({ ...s, price_sell: e.target.value }))}
                  className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-sm font-medium text-navy">Lat</label>
                  <input
                    type="number"
                    step="0.01"
                    value={fveForm.lat}
                    onChange={(e) => setFveForm((s) => ({ ...s, lat: e.target.value }))}
                    className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-navy">Lon</label>
                  <input
                    type="number"
                    step="0.01"
                    value={fveForm.lon}
                    onChange={(e) => setFveForm((s) => ({ ...s, lon: e.target.value }))}
                    className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm"
                  />
                </div>
              </div>
            </div>
            <button
              onClick={handleSaveParams}
              disabled={busy === "saveParams"}
              className="btn-primary mt-4 text-sm disabled:opacity-60"
            >
              {busy === "saveParams" ? "Ukládám..." : "Uložit parametry"}
            </button>
          </div>
        </div>
      )}

      {/* Náhled tab */}
      {active === "preview" && (
        <div className="space-y-6">
          {!dataPreview ? (
            <div className="card p-8 text-center text-sm text-slateMuted">
              Nejdříve nahrajte data v záložce Data.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="kpi-card border-l-antelonGreen">
                  <p className="text-xs text-slateMuted uppercase">Ø denně</p>
                  <p className="text-2xl font-bold text-navy">{avg_daily !== undefined ? `${Number(avg_daily).toFixed(1)} kWh` : "—"}</p>
                  <p className="text-xs text-slateMuted mt-1">celkem {total_kwh !== undefined ? `${Number(total_kwh).toFixed(0)} kWh` : "—"} / {n_complete ?? "—"} dní</p>
                </div>
                <div className="kpi-card border-l-navy">
                  <p className="text-xs text-slateMuted uppercase">Roční odhad</p>
                  <p className="text-2xl font-bold text-navy">{annual_mwh !== undefined ? `${Number(annual_mwh).toFixed(1)} MWh` : "—"}</p>
                </div>
                <div className="kpi-card border-l-antelonOrange">
                  <p className="text-xs text-slateMuted uppercase">Pracovní vs víkend</p>
                  <p className="text-sm font-bold text-navy mt-1">
                    {weekday_avg !== undefined ? `${Number(weekday_avg).toFixed(1)}` : "—"} / {weekend_avg !== undefined ? `${Number(weekend_avg).toFixed(1)}` : "—"} kWh
                  </p>
                </div>
                <div className="kpi-card border-l-slateMuted">
                  <p className="text-xs text-slateMuted uppercase">Fáze A/B/C</p>
                  <p className="text-sm font-bold text-navy mt-1">
                    {phasePct.A !== undefined ? `${Number(phasePct.A).toFixed(0)}%` : "—"} /{" "}
                    {phasePct.B !== undefined ? `${Number(phasePct.B).toFixed(0)}%` : "—"} /{" "}
                    {phasePct.C !== undefined ? `${Number(phasePct.C).toFixed(0)}%` : "—"}
                  </p>
                </div>
              </div>

              {/* green/red */}
              {(dataPreview.green_kwh !== undefined || dataPreview.red_kwh !== undefined) && (
                <div className="grid sm:grid-cols-3 gap-4">
                  <div className="card p-4 border-l-4 border-l-antelonGreen">
                    <p className="text-xs text-slateMuted">Zelená (přebytek)</p>
                    <p className="text-lg font-bold text-antelonGreen">
                      {dataPreview.green_kwh !== undefined ? `${Number(dataPreview.green_kwh).toFixed(1)} kWh/den` : "—"}
                    </p>
                  </div>
                  <div className="card p-4 border-l-4 border-l-red-500">
                    <p className="text-xs text-slateMuted">Červená (deficit)</p>
                    <p className="text-lg font-bold text-red-600">
                      {dataPreview.red_kwh !== undefined ? `${Number(dataPreview.red_kwh).toFixed(1)} kWh/den` : "—"}
                    </p>
                  </div>
                  <div className="card p-4 border-l-4 border-l-navy">
                    <p className="text-xs text-slateMuted">Bilance</p>
                    <p className="text-sm font-bold text-navy">
                      {dataPreview.green_kwh !== undefined && dataPreview.red_kwh !== undefined
                        ? `${(Number(dataPreview.green_kwh) - Number(dataPreview.red_kwh)).toFixed(1)} kWh`
                        : "—"}
                    </p>
                  </div>
                </div>
              )}

              {warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                  <p className="text-sm font-semibold text-amber-800">Varování</p>
                  <ul className="text-sm text-amber-700 list-disc pl-5 mt-1">
                    {warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {gaps.length > 0 && (
                <div className="bg-slate-50 border rounded-lg p-4">
                  <p className="text-sm font-semibold text-navy">Mezery</p>
                  <p className="text-sm text-slateMuted">{gaps.join(", ")}</p>
                </div>
              )}

              <div className="card p-5">
                <h4 className="font-semibold text-navy">Poznámka k teaser</h4>
                <p className="text-sm text-slateMuted mt-1">
                  Pro přihlášeného a přiřazeného uživatele je náhled bez blur. Anonymní / nepropojený uživatel vidí teaser sekce rozostřené (blur 6px) — viz veřejný náhled.
                </p>
                <div className="mt-4 grid sm:grid-cols-2 gap-4">
                  <div className="border rounded-lg p-4">
                    <p className="text-xs font-semibold text-navy">Ukázka bez blur (aktuální login)</p>
                    <div className="mt-2 bg-slate-50 rounded p-3 text-sm">
                      Doporučení: FVE 25 kWp + baterie 15–20 kWh, roční výroba ~25 MWh, pokrytí ~60 %.
                    </div>
                  </div>
                  <div className="border rounded-lg p-4">
                    <p className="text-xs font-semibold text-navy">Ukázka teaser (blur)</p>
                    <div className="mt-2 bg-slate-50 rounded p-3 text-sm blur-teaser">
                      Doporučení: FVE 25 kWp + baterie 15–20 kWh, roční výroba ~25 MWh, pokrytí ~60 %.
                    </div>
                    <p className="text-xs text-amber-600 mt-1">🔒 Dostupné po připojení</p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* PDF tab */}
      {active === "pdf" && (
        <div className="space-y-6">
          <div className="card p-5 border-l-4 border-l-antelonGreen">
            <h3 className="font-semibold text-navy">Generovat PDF</h3>
            <p className="text-xs text-slateMuted mt-1">Každé generování vytvoří novou verzi s vodotiskem dle role.</p>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
              {[
                { id: "antelon", label: "Antelon", desc: "Pentagon 11 stran 16:9", color: "bg-navy" },
                { id: "energy", label: "Energy", desc: "fveAnalyzator", color: "bg-antelonGreen" },
                { id: "economic", label: "Economic", desc: "fveAnalyzator", color: "bg-antelonOrange" },
                { id: "ote", label: "OTE", desc: "spot ceny", color: "bg-slateMuted" },
              ].map((tpl) => (
                <button
                  key={tpl.id}
                  onClick={() => handleGenerate(tpl.id)}
                  disabled={busy === `gen-${tpl.id}`}
                  className={`${tpl.color} text-white rounded-lg p-4 text-left hover:brightness-110 transition disabled:opacity-60`}
                >
                  <p className="font-semibold text-sm">{tpl.label}</p>
                  <p className="text-xs opacity-80">{tpl.desc}</p>
                  <p className="text-xs mt-2 font-medium">
                    {busy === `gen-${tpl.id}` ? "Generuji..." : "Generovat →"}
                  </p>
                </button>
              ))}
            </div>
          </div>

          <div className="card p-5">
            <h3 className="font-semibold text-navy mb-3">Verze ({pdfs.length})</h3>
            {pdfs.length === 0 ? (
              <p className="text-sm text-slateMuted">Zatím žádné PDF. Vygenerujte první verzi.</p>
            ) : (
              <div className="divide-y">
                {pdfs.map((pdf) => (
                  <div key={String(pdf.id)} className="flex items-center justify-between py-3">
                    <div>
                      <p className="text-sm font-medium text-navy">
                        {pdf.template} <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">v{String(pdf.version)}</span>
                        {pdf.audience && <span className="text-xs text-slateMuted ml-2">{pdf.audience}</span>}
                      </p>
                      <p className="text-xs text-slateMuted">
                        {pdf.created_at ? new Date(pdf.created_at).toLocaleString("cs-CZ") : ""}
                      </p>
                    </div>
                    <button onClick={() => handleDownload(pdf.id)} className="btn-secondary text-xs">
                      Stáhnout PDF
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Photos tab */}
      {active === "photos" && (
        <div className="space-y-6">
          <div className="card p-5 border-l-4 border-l-antelonOrange">
            <h3 className="font-semibold text-navy">Nahrát fotku</h3>
            <div className="mt-3 flex flex-col sm:flex-row gap-3">
              <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                className="block w-full text-sm text-slateMuted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-navy file:text-white file:text-sm"
                onChange={(e) => handlePhotoUpload(e.target.files)}
              />
              <input
                value={photoCaption}
                onChange={(e) => setPhotoCaption(e.target.value)}
                placeholder="Popisek (volitelné)"
                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            {busy === "photo" && <p className="text-xs text-slateMuted mt-2">Nahrávám...</p>}
          </div>

          <div className="card p-5">
            <h3 className="font-semibold text-navy mb-3">Galerie ({photos.length})</h3>
            {photos.length === 0 ? (
              <p className="text-sm text-slateMuted">Žádné fotky.</p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {photos.map((ph) => (
                  <div key={String(ph.id)} className="border rounded-lg overflow-hidden bg-white">
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    <img
                      src={(ph.url as string) || (ph.path as string) || ""}
                      alt={ph.caption || ph.filename}
                      className="w-full h-32 object-cover bg-slate-100"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                    <div className="p-2">
                      <p className="text-xs font-medium text-navy truncate">{ph.filename}</p>
                      {ph.caption && <p className="text-xs text-slateMuted truncate">{ph.caption}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Share tab */}
      {active === "share" && (
        <div className="space-y-6">
          <div className="card p-6 border-l-4 border-l-antelonGreen">
            <h3 className="font-semibold text-navy">Sdílení se zákazníkem</h3>
            <p className="text-sm text-slateMuted mt-1">
              Vytvořte share kód, QR a odkaz <code className="bg-slate-100 px-1 rounded">/p/{"{code}"}</code> pro připojení zákazníka.
            </p>

            <div className="mt-4 flex flex-wrap gap-3">
              <button onClick={handleCreateShare} disabled={busy === "share"} className="btn-primary text-sm disabled:opacity-60">
                {busy === "share" ? "Vytvářím..." : share?.code ? "Obnovit sdílení" : "Vytvořit sdílení"}
              </button>
              {share?.code && (
                <button onClick={handleJoin} disabled={busy === "join"} className="btn-secondary text-sm disabled:opacity-60">
                  {busy === "join" ? "Připojuji..." : "Připojit se (test)"}
                </button>
              )}
            </div>

            {share?.code ? (
              <div className="mt-6 grid sm:grid-cols-2 gap-6">
                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-semibold text-slateMuted uppercase">Kód</p>
                    <p className="text-2xl font-mono font-bold tracking-widest text-navy mt-1">{share.code}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slateMuted uppercase">Odkaz</p>
                    <a
                      href={share.url || `${window.location.origin}/p/${share.code}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-antelonGreen hover:underline break-all"
                    >
                      {share.url || `${window.location.origin}/p/${share.code}`}
                    </a>
                  </div>
                  <div className="flex gap-2">
                    <Link to={`/p/${share.code}`} target="_blank" className="btn-secondary text-xs">
                      Otevřít náhled
                    </Link>
                    <button
                      onClick={() => {
                        if (share.code) navigator.clipboard.writeText(share.code);
                      }}
                      className="btn-secondary text-xs"
                    >
                      Kopírovat kód
                    </button>
                  </div>
                </div>

                <div className="flex flex-col items-center">
                  <p className="text-xs font-semibold text-slateMuted uppercase mb-2">QR kód</p>
                  {share.qr_b64 ? (
                    <img
                      src={share.qr_b64.startsWith("data:") ? share.qr_b64 : `data:image/png;base64,${share.qr_b64}`}
                      alt="QR"
                      className="w-40 h-40 border rounded-lg bg-white object-contain p-2"
                    />
                  ) : (
                    <div className="w-40 h-40 border rounded-lg bg-slate-50 flex items-center justify-center text-xs text-slateMuted">
                      QR bude po vytvoření
                    </div>
                  )}
                  <p className="text-xs text-slateMuted mt-2 text-center">Zákazník naskenuje QR → /p/{share.code}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slateMuted mt-4">Zatím žádné sdílení — klikněte na Vytvořit.</p>
            )}
          </div>

          <div className="card p-5">
            <h4 className="font-semibold text-navy">Jak to funguje</h4>
            <ol className="text-sm text-slateMuted list-decimal pl-5 mt-2 space-y-1">
              <li>Zaměstnanec vytvoří projekt a share kód.</li>
              <li>Zákazník se zaregistruje a otevře odkaz /p/{"{code}"}.</li>
              <li>Klikne „Připojit se k projektu“ → záznam v project_users.</li>
              <li>Od té doby vidí plný náhled a čisté PDF bez vodotisku/blur.</li>
              <li>Anonym vidí teaser s blur a CTA registrace; PDF má vodotisk.</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
