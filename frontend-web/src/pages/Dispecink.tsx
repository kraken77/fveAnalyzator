import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { hasAnyRole, useAuth } from "../context/AuthContext";
import { BOARD_PHASES, groupStepsByBoardPhase } from "../constants/pipelinePhases";
import { Tooltip } from "../components/ui/Tooltip";
import {
  getPipeline,
  importDispecink,
  listProjects,
} from "../api/pipeline";
import type { PipelineStep, ProjectLite } from "../types";

type StatusColor = Record<string, string>;

const STATUS_COLORS: StatusColor = {
  done: "bg-emerald-500",
  signed: "bg-emerald-500",
  sent: "bg-amber-300",
  in_progress: "bg-amber-400",
  planned: "bg-sky-400",
  cancelled: "bg-slate-300",
  skipped: "bg-slate-200 ring-1 ring-inset ring-slate-300",
  not_applicable: "bg-slate-200",
  not_started: "bg-white ring-1 ring-inset ring-slate-300",
};

const TYPE_LABELS: Record<string, string> = {
  rd: "Rodinný dům",
  byt: "Bytový dům",
  firma: "Firma / podnikání",
  obec: "Obec",
  ostatni: "Ostatní",
};

interface BoardRow {
  project: ProjectLite;
  steps: PipelineStep[];
  doneCount: number;
  total: number;
}

const CONCURRENCY = 8;
async function pool<T>(items: T[], worker: (item: T) => Promise<void>, size = CONCURRENCY) {
  const queue = [...items];
  async function run() {
    while (queue.length) {
      const item = queue.shift()!;
      await worker(item);
    }
  }
  const workers = Array.from({ length: Math.min(size, items.length) }, run);
  await Promise.all(workers);
}

export default function Dispecink() {
  const { user } = useAuth();
  const isAdmin = hasAnyRole(user, ["admin"]);
  const [projects, setProjects] = useState<ProjectLite[]>([]);
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fType, setFType] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fQuery, setFQuery] = useState("");
  const [fPerson, setFPerson] = useState("");

  const [busyImport, setBusyImport] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listProjects();
      setProjects(list);

      const results: BoardRow[] = [];
      let cursor = 0;
      await pool(list, async (p) => {
        try {
          const view = await getPipeline(p.id);
          const steps = view.steps.filter((s) => !s.hidden);
          results.push({
            project: p,
            steps,
            doneCount: steps.filter((s) =>
            ["done", "signed", "skipped", "not_applicable"].includes(s.status),
          ).length,
            total: steps.length,
          });
        } catch {
          results.push({ project: p, steps: [], doneCount: 0, total: 0 });
        }
        cursor += 1;
      });
      const byId = new Map(list.map((p) => [String(p.id), p]));
      setRows(
        results
          .sort((a, b) => String(a.project.id).localeCompare(String(b.project.id)))
          .map((r) => ({ ...r, project: byId.get(String(r.project.id)) ?? r.project })),
      );
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : "Chyba načtení");
      setError(m);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (fType && (r.project.type || "") !== fType) return false;
      if (fStatus && (r.project.status || "") !== fStatus) return false;
      if (fPerson) {
        const active = r.steps.some(
          (s) =>
            String(s.assigned_user_id ?? "") === fPerson &&
            (s.status === "planned" || s.status === "in_progress"),
        );
        if (!active) return false;
      }
      if (fQuery) {
        const q = fQuery.toLowerCase();
        const hay = `${r.project.name} ${r.project.customer_name ?? ""} ${r.project.share_code ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rows, fType, fStatus, fQuery, fPerson]);

  const people = useMemo(() => {
    const m = new Map<string, { id: string; name: string }>();
    rows.forEach((r) =>
      r.steps.forEach((s) => {
        if (!s.assigned_user_id) return;
        const id = String(s.assigned_user_id);
        if (!m.has(id)) {
          m.set(id, { id, name: s.assigned_name || `Uživatel #${id}` });
        }
      }),
    );
    return Array.from(m.values());
  }, [rows]);

  const types = useMemo(() => {
    const s = new Set(projects.map((p) => p.type || "").filter(Boolean));
    return Array.from(s);
  }, [projects]);

  const handleImport = async (file: File | undefined) => {
    if (!file) return;
    setBusyImport(true);
    setMsg(null);
    try {
      const res = await importDispecink(file);
      setMsg(`Import OK: ${res.imported ?? "?"} projektů${res.skipped ? `, přeskočeno ${res.skipped}` : ""}`);
      await load();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Import selhal";
      setMsg(m);
    } finally {
      setBusyImport(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">Dispečink — tabule zakázek</h1>
          <p className="text-sm text-slateMuted mt-0.5">
            {filtered.length} z {rows.length} projektů
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={(e) => handleImport(e.target.files?.[0])}
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={busyImport}
                className="btn-navy text-sm disabled:opacity-60"
              >
                {busyImport ? "Importuji..." : "Import PROČESNÍ DISPEČINK.xlsx"}
              </button>
            </>
          )}
          <Link to="/projects" className="btn-secondary text-sm">
            Nová zakázka
          </Link>
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
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded">
          {error}
        </div>
      )}

      {/* filtry */}
      <div className="card p-4 flex flex-col sm:flex-row gap-3">
        <input
          value={fQuery}
          onChange={(e) => setFQuery(e.target.value)}
          placeholder="Hledat název / zákazníka / kód..."
          className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-antelonGreen focus:outline-none"
        />
        <select
          value={fType}
          onChange={(e) => setFType(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">Všechny typy</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {TYPE_LABELS[t] ?? t}
            </option>
          ))}
        </select>
        <select
          value={fStatus}
          onChange={(e) => setFStatus(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">Všechny stavy</option>
          <option value="active">active</option>
          <option value="cancelled">cancelled</option>
          <option value="done">done</option>
        </select>
        <select
          value={fPerson}
          onChange={(e) => setFPerson(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">Všichni uživatelé</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="animate-pulse space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 bg-slate-200 rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="card overflow-x-auto" data-testid="board">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slateMuted">
              <tr>
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Zakázka</th>
                <th className="px-3 py-2 hidden md:table-cell">Typ</th>
                <th className="px-3 py-2">Stav</th>
                {BOARD_PHASES.map((p) => (
                  <th key={p.key} className="px-2 py-2 whitespace-nowrap">
                    {p.label}
                  </th>
                ))}
                <th className="px-3 py-2 text-right">Hotovo</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={String(r.project.id)} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-2 text-slateMuted">{String(r.project.id)}</td>
                  <td className="px-3 py-2">
                    <Link
                      to={`/projects/${r.project.id}/pipeline`}
                      className="font-medium text-navy hover:text-antelonGreen"
                    >
                      {r.project.name}
                    </Link>
                    <p className="text-xs text-slateMuted">{r.project.customer_name || "—"}</p>
                  </td>
                  <td className="px-3 py-2 hidden md:table-cell">
                    <span className="text-xs bg-slate-100 border border-slate-200 rounded px-2 py-0.5">
                      {TYPE_LABELS[r.project.type ?? ""] ?? r.project.type ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded ${
                        r.project.status === "cancelled"
                          ? "bg-slate-200 text-slate-600"
                          : r.project.status === "done"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-antelonGreen/15 text-antelonGreen"
                      }`}
                    >
                      {r.project.status ?? "—"}
                    </span>
                  </td>
                  {groupStepsByBoardPhase(r.steps).map(([phaseKey, phaseSteps]) => (
                    <td key={phaseKey} data-testid={`cell-${phaseKey}`} className="px-2 py-2">
                      <div className="flex items-center gap-0.5 flex-wrap">
                        {phaseSteps.map((s) => (
                          <Tooltip key={String(s.id)} content={`${s.name} (${s.status})`}>
                            <Link
                              to={`/projects/${r.project.id}/pipeline?phase=${phaseKey}&stepId=${s.id}`}
                              className={`w-2.5 h-5 rounded-sm ${STATUS_COLORS[s.status] ?? "bg-slate-200"}`}
                            />
                          </Tooltip>
                        ))}
                        {phaseKey === "lead" && r.total === 0 && (
                          <span className="text-xs text-slate-400">bez šablony</span>
                        )}
                      </div>
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right">
                    <span className="text-xs font-semibold">
                      {r.doneCount}/{r.total}
                    </span>
                    <div className="w-16 ml-auto mt-0.5 h-1.5 bg-slate-100 rounded overflow-hidden">
                      <div
                        className="h-full bg-antelonGreen rounded"
                        style={{ width: r.total ? `${(r.doneCount / r.total) * 100}%` : "0%" }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4 + BOARD_PHASES.length + 1} className="px-3 py-8 text-center text-slate-400 text-sm">
                    Žádné zakázky.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center gap-3 text-xs text-slateMuted">
        <span className="flex items-center gap-1"><span className="w-2.5 h-5 rounded-sm bg-emerald-500" /> done</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-5 rounded-sm bg-amber-400" /> in_progress</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-5 rounded-sm bg-sky-400" /> planned</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-5 rounded-sm bg-white ring-1 ring-inset ring-slate-300" /> not_started</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-5 rounded-sm bg-slate-300" /> cancelled / skipped</span>
      </div>
    </div>
  );
}