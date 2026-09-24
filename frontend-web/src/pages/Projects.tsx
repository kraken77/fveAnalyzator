import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";

interface Project {
  id: number | string;
  name: string;
  customer_name?: string;
  description?: string;
  share_code?: string;
  owner_id?: number | string;
  created_at?: string;
  updated_at?: string;
}

export default function Projects() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", customer_name: "", description: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const canCreate = user?.role === "admin" || user?.role === "antelon";

  const fetchProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await client.get("/projects");
      const data = res.data as unknown;
      // normalize: could be {projects: []} or []
      const list: Project[] = Array.isArray(data)
        ? (data as Project[])
        : ((data as { projects?: Project[] })?.projects ?? []);
      setProjects(list);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err instanceof Error ? err.message : "Nepodařilo se načíst projekty");
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setCreateError("Název je povinný");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await client.post("/projects", {
        name: form.name.trim(),
        customer_name: form.customer_name.trim() || undefined,
        description: form.description.trim() || undefined,
      });
      setForm({ name: "", customer_name: "", description: "" });
      setShowCreate(false);
      await fetchProjects();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err instanceof Error ? err.message : "Chyba při vytváření");
      setCreateError(msg);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-navy">Projekty</h1>
          <p className="text-sm text-slateMuted mt-1">
            Přehled zákaznických projektů ReportGen — FVE {projects.length} projektů
          </p>
        </div>
        {canCreate ? (
          <button onClick={() => setShowCreate((v) => !v)} className="btn-primary self-start sm:self-auto">
            + Nový projekt
          </button>
        ) : (
          <div className="text-xs text-slate-500 bg-white border px-3 py-2 rounded-lg">
            Vytvářet projekty může pouze role antelon / admin
          </div>
        )}
      </div>

      {showCreate && canCreate && (
        <form
          onSubmit={handleCreate}
          className="card p-5 sm:p-6 border-l-4 border-l-antelonGreen space-y-4"
        >
          <h3 className="font-semibold text-navy">Nový projekt</h3>
          {createError && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded">
              {createError}
            </div>
          )}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Název *</label>
              <input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Pentagon — administrativní budova"
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-navy mb-1">Zákazník</label>
              <input
                value={form.customer_name}
                onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))}
                placeholder="Antelon Energy s.r.o."
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-navy mb-1">Popis</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              rows={2}
              placeholder="Krátký popis projektu..."
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">
              Zrušit
            </button>
            <button type="submit" disabled={creating} className="btn-primary disabled:opacity-60">
              {creating ? "Vytvářím..." : "Vytvořit"}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-5 animate-pulse">
              <div className="h-5 bg-slate-100 rounded w-3/4 mb-3" />
              <div className="h-4 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="card p-6 text-center">
          <p className="text-red-600 text-sm mb-3">{error}</p>
          <button onClick={fetchProjects} className="btn-secondary text-sm">
            Zkusit znovu
          </button>
        </div>
      ) : projects.length === 0 ? (
        <div className="card p-10 text-center border-l-4 border-l-antelonOrange">
          <p className="text-navy font-semibold">Žádné projekty</p>
          <p className="text-sm text-slateMuted mt-1">
            {canCreate
              ? "Vytvořte první projekt tlačítkem výše."
              : "Zatím nejste přiřazeni k žádnému projektu. Požádejte kolegu o sdílecí odkaz."}
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {projects.map((p) => (
            <div
              key={String(p.id)}
              className="card p-5 border-l-4 border-l-antelonGreen hover:shadow-md transition group"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-navy group-hover:text-antelonGreen transition line-clamp-2">
                  {p.name}
                </h3>
                {p.share_code && (
                  <span className="text-[11px] font-mono bg-navy text-white px-2 py-1 rounded">
                    {p.share_code}
                  </span>
                )}
              </div>
              {p.customer_name && (
                <p className="text-sm text-slateMuted mt-1">{p.customer_name}</p>
              )}
              {p.description && (
                <p className="text-xs text-slate-500 mt-2 line-clamp-2">{p.description}</p>
              )}
              <div className="flex items-center justify-between mt-4 gap-2">
                <span className="text-xs text-slate-400">
                  {p.created_at ? new Date(p.created_at).toLocaleDateString("cs-CZ") : ""}
                </span>
                <div className="flex items-center gap-2">
                  <Link
                    to={`/projects/${p.id}/pipeline`}
                    className="text-xs font-medium text-antelonGreen hover:underline"
                    title="Procesní pipeline"
                  >
                    Pipeline →
                  </Link>
                  <Link
                    to={`/projects/${p.id}`}
                    className="text-xs font-medium text-navy hover:text-antelonGreen hover:underline"
                  >
                    Projekt →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
