import { useCallback, useEffect, useMemo, useState } from "react";
import { hasAnyRole, useAuth } from "../context/AuthContext";
import {
  getOverview,
  simulate,
  listCrews,
  createCrew,
  updateCrew,
} from "../api/planning";
import type {
  PlanningOverview,
  PlanningItem,
  WorkCrew,
  SimulateResponse,
} from "../api/planning";

// ---------- Pomocné funkce ----------

function addDays(date: string, n: number): string {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  const da = new Date(a);
  const db = new Date(b);
  return Math.round((db.getTime() - da.getTime()) / 86400_000);
}

function formatDate(cs: string): string {
  const d = new Date(cs);
  return `${String(d.getDate()).padStart(2, "0")}. ${String(d.getMonth() + 1).padStart(2, "0")}. ${d.getFullYear()}`;
}

function isWeekend(date: string): boolean {
  const d = new Date(date);
  return d.getDay() === 0 || d.getDay() === 6;
}

function isFirm(kind: string): boolean {
  return kind === "firm";
}

const WORK_DAY_MAP: Record<string, string> = {
  po: "Po",
  ut: "Út",
  st: "St",
  ct: "Čt",
  pa: "Pá",
  so: "So",
  ne: "Ne",
};

const WORK_TYPE_LABEL: Record<string, string> = {
  roofer: "Montáž",
  electrician: "Elektro",
};

const WORK_TYPE_COLORS: Record<string, string> = {
  roofer: "bg-emerald-500",
  electrician: "bg-sky-500",
};

function workTypeColor(wt: string): string {
  return WORK_TYPE_COLORS[wt] ?? "bg-amber-400";
}

// ---------- Gantt data helpers ----------

const GANTT_DAYS = 90;

function buildDayLabels(today: string) {
  const days: { date: string; month: number; dayInMonth: number }[] = [];
  for (let i = 0; i < GANTT_DAYS; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    days.push({
      date: d.toISOString().slice(0, 10),
      month: d.getMonth(),
      dayInMonth: d.getDate(),
    });
  }
  return days;
}

// ---------- Gantt ----------

function GanttChart({
  overview,
  sim,
}: {
  overview: PlanningOverview;
  sim: SimulateResponse | null;
}) {
  const data = sim ?? overview;
  const days = useMemo(() => buildDayLabels(overview.today), [overview.today]);
  const dayIndex = useMemo(() => {
    const m = new Map<string, number>();
    days.forEach((d, i) => m.set(d.date, i));
    return (t: string | null | undefined) => (t ? m.get(t) ?? -1 : -1);
  }, [days]);
  const holidays = overview.holidays_in_range;
  const today = overview.today;

  const sortedProjects = useMemo(() => {
    const firmItems = data.items.filter((i) => i.kind === "firm");
    const reserveItems = data.items.filter(
      (i) => i.kind === "reserve" || i.kind === "expired"
    );
    const firmMap = new Map<number | string, PlanningItem[]>();
    const reserveMap = new Map<number | string, PlanningItem[]>();
    for (const item of firmItems) {
      if (!firmMap.has(item.project_id)) firmMap.set(item.project_id, []);
      firmMap.get(item.project_id)!.push(item);
    }
    for (const item of reserveItems) {
      if (!reserveMap.has(item.project_id)) reserveMap.set(item.project_id, []);
      reserveMap.get(item.project_id)!.push(item);
    }
    // Filmy seřazené podle data SoD (nejstarší potvrzené nahoře —
    // stejné pořadí, v jakém jim scheduler přiděluje čety), bez SoD na konec.
    const sodOf = (pid: number | string) =>
      overview.projects.find((p) => p.id === pid)?.sod_date ?? "9999-12-31";
    const firmArr = Array.from(firmMap.entries()).sort(
      (a, b) =>
        sodOf(a[0]).localeCompare(sodOf(b[0])) ||
        Number(a[0]) - Number(b[0])
    );
    const reserveArr = Array.from(reserveMap.entries()).sort(
      (a, b) => Number(a[0]) - Number(b[0])
    );
    return [...firmArr, ...reserveArr];
  }, [data.items, overview.projects]);

  return (
    <div className="card overflow-x-auto" data-testid="gantt-chart">
      <div className="min-w-[900px]">
        {/* Header: month + days */}
        <div className="flex border-b border-slate-200">
          <div className="sticky left-0 z-20 bg-white border-r border-slate-200 w-48 min-w-[12rem] flex-shrink-0 p-2 text-xs font-semibold text-slateMuted uppercase">
            Zakázka
          </div>
          <div className="flex-1">
            {/* Month row */}
            <div className="flex border-b border-slate-100">
              {days.map((d, i) => {
                if (i > 0 && days[i - 1].month === d.month) return null;
                let count = 0;
                for (let j = i; j < days.length && days[j].month === d.month; j++)
                  count++;
                const monthNames = [
                  "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
                  "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
                ];
                return (
                  <div
                    key={i}
                    className="text-center text-[10px] font-semibold text-slateMuted py-0.5 border-r border-slate-50 bg-slate-50"
                    style={{ minWidth: count * 40, flex: count }}
                  >
                    {monthNames[d.month]}
                  </div>
                );
              })}
            </div>
            {/* Day row */}
            <div className="flex">
              {days.map((d, i) => {
                const wknd = isWeekend(d.date);
                const hol = holidays.includes(d.date);
                const isToday = d.date === today;
                return (
                  <div
                    key={i}
                    className={`w-[40px] h-5 text-[10px] text-center leading-5 border-r border-slate-100 ${
                      wknd || hol ? "bg-slate-100 text-slate-400" : "text-slateMuted"
                    } ${isToday ? "bg-emerald-50 text-emerald-700 font-bold" : ""}`}
                    title={d.date}
                  >
                    {d.dayInMonth}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Project rows */}
        {sortedProjects.map(([projId, items]) => {
          const projInfo =
            overview.projects.find((p) => p.id === projId) ??
            data.projects.find((p) => p.id === projId);
          const isF = items[0]?.kind === "firm";
          return (
            <div
              key={String(projId)}
              className={`flex border-b border-slate-100 hover:bg-slate-50 ${isF ? "bg-white" : "bg-amber-50/30"}`}
            >
              <div className="sticky left-0 z-10 bg-white border-r border-slate-200 w-48 min-w-[12rem] flex-shrink-0 px-3 py-1.5 text-sm text-navy font-medium flex items-center gap-1.5">
                <span>{projInfo?.name || `Projekt #${projId}`}</span>
                {isF ? (
                  <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1 rounded">
                    film
                  </span>
                ) : (
                  <span className="text-[10px] bg-slate-200 text-slate-600 px-1 rounded">
                    rez
                  </span>
                )}
              </div>
              <div className="flex-1 relative" style={{ height: 32 }}>
                {days.map((_, i) => (
                  <div
                    key={i}
                    className="absolute top-0 bottom-0 border-r border-slate-50"
                    style={{ left: i * 40 }}
                  />
                ))}
                {/* Today line */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-emerald-500 z-10"
                  style={{ left: dayIndex(today) * 40 + 20 }}
                  title={`Dnes (${today})`}
                />
                {items.map((item, idx) => {
                  const si = dayIndex(item.start);
                  const ei = dayIndex(item.end);
                  if (si < 0) {
                    return (
                      <div
                        key={`${item.step_code}-${idx}`}
                        className="absolute top-1 h-6 bg-slate-200 rounded text-[9px] text-slate-500 flex items-center px-2 truncate z-5"
                        style={{ left: 4, right: 4 }}
                        title="Bez pracovní čety"
                      >
                        bez čteta
                      </div>
                    );
                  }
                  const width = Math.max((ei - si + 1) * 40 - 2, 20);
                  const colorClass = workTypeColor(item.work_type);
                  return (
                    <div
                      key={`${item.step_code}-${idx}`}
                      className={`absolute top-1 h-6 rounded flex items-center px-1.5 text-[9px] text-white truncate font-medium z-5 ${colorClass} ${!isF ? "opacity-50" : ""}`}
                      style={{ left: si * 40 + 1, width }}
                      title={`${item.step_name}: ${item.start}${item.end ? ` → ${item.end}` : ""}${item.crew_name ? `\nČeta: ${item.crew_name}` : ""}`}
                    >
                      {item.step_name}
                      {item.crew_name && (
                        <span className="ml-1 opacity-70">({item.crew_name})</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {sortedProjects.length === 0 && (
          <div className="p-8 text-center text-slate-400 text-sm">
            Žádné projekty v období.
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- Kalendář ----------

function CalendarMonth({
  overview,
  sim,
}: {
  overview: PlanningOverview;
  sim: SimulateResponse | null;
}) {
  const data = sim ?? overview;
  const [month, setMonth] = useState(() => new Date(overview.today));
  const items = data.items;

  const itemsByDate = useMemo(() => {
    const map = new Map<string, PlanningItem[]>();
    const days = buildDayLabels(overview.today);
    const idx = new Map<string, number>();
    days.forEach((d, i) => idx.set(d.date, i));
    for (const item of items) {
      if (!item.start || !item.end) continue;
      const di = idx.get(item.start);
      const de = idx.get(item.end);
      if (di === undefined || de === undefined) continue;
      for (let i = di; i <= de; i++) {
        const dateStr = days[i]?.date;
        if (dateStr) {
          if (!map.has(dateStr)) map.set(dateStr, []);
          map.get(dateStr)!.push(item);
        }
      }
    }
    return map;
  }, [items, overview.today]);

  const year = month.getFullYear();
  const m = month.getMonth();
  const firstDay = new Date(year, m, 1).getDay();
  const daysInMonth = new Date(year, m + 1, 0).getDate();
  const adjustedFirst = firstDay === 0 ? 6 : firstDay - 1;

  const monthNames = [
    "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
    "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
  ];
  const dayNames = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];

  const [filterCrew, setFilterCrew] = useState("");
  const [filterKind, setFilterKind] = useState("");

  return (
    <div className="card p-4" data-testid="calendar">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMonth(new Date(year, m - 1, 1))}
            className="text-sm px-2 py-1 hover:bg-slate-100 rounded"
          >
            ←
          </button>
          <span className="font-semibold text-sm">{monthNames[m]} {year}</span>
          <button
            onClick={() => setMonth(new Date(year, m + 1, 1))}
            className="text-sm px-2 py-1 hover:bg-slate-100 rounded"
          >
            →
          </button>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filterCrew}
            onChange={(e) => setFilterCrew(e.target.value)}
            className="text-xs border border-slate-200 rounded px-2 py-1"
          >
            <option value="">Všechny čety</option>
            {overview.crews.map((c) => (
              <option key={c.id} value={c.name}>{c.name}</option>
            ))}
          </select>
          <select
            value={filterKind}
            onChange={(e) => setFilterKind(e.target.value)}
            className="text-xs border border-slate-200 rounded px-2 py-1"
          >
            <option value="">Všechny typy</option>
            <option value="firm">Filmy</option>
            <option value="reserve">Rezervace</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-px bg-slate-200 border border-slate-200 rounded overflow-hidden">
        {dayNames.map((dn) => (
          <div
            key={dn}
            className="bg-slate-50 text-xs text-center py-1.5 text-slateMuted font-medium"
          >
            {dn}
          </div>
        ))}
        {Array.from({ length: adjustedFirst }).map((_, i) => (
          <div key={`empty-${i}`} className="bg-white h-20" />
        ))}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const dayNum = i + 1;
          const date = `${year}-${String(m + 1).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
          const dayItems = itemsByDate.get(date) ?? [];
          const isToday = date === overview.today;
          const wknd = isWeekend(date);
          const hol = overview.holidays_in_range.includes(date);

          let filtered = dayItems;
          if (filterCrew) filtered = filtered.filter((it) => it.crew_name === filterCrew);
          if (filterKind) filtered = filtered.filter((it) => it.kind === filterKind);

          return (
            <div
              key={date}
              className={`bg-white h-20 p-1 text-xs overflow-hidden ${isToday ? "ring-2 ring-emerald-400 z-10" : wknd || hol ? "bg-slate-50" : ""}`}
            >
              <div className={`font-medium ${isToday ? "text-emerald-600" : wknd || hol ? "text-slate-400" : "text-navy"}`}>
                {dayNum}
              </div>
              {filtered.slice(0, 3).map((item, idx) => (
                <div
                  key={idx}
                  className={`mt-0.5 px-1 py-0.5 rounded text-[10px] truncate text-white ${workTypeColor(item.work_type)} ${isFirm(item.kind) ? "" : "opacity-50"}`}
                  title={`${item.project_name} — ${item.step_name}${item.crew_name ? `\nČeta: ${item.crew_name}` : ""}`}
                >
                  {item.step_name}
                </div>
              ))}
              {filtered.length > 3 && (
                <div className="text-[9px] text-slate-400">+{filtered.length - 3} více</div>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-2 text-xs">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-emerald-500" /> Montáž
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-sky-500" /> Elektro
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-slate-300" /> Víkend/svátek
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded opacity-50" /> Rezervace
        </span>
      </div>
    </div>
  );
}

// ---------- Panel čteta (editace) ----------

function CrewEditor({
  crews,
  onAdd,
  onUpdate,
  today,
}: {
  crews: WorkCrew[];
  onAdd: (c: Partial<WorkCrew>) => Promise<void>;
  onUpdate: (id: number, c: Partial<WorkCrew>) => Promise<void>;
  today: string;
}) {
  const [editing, setEditing] = useState<WorkCrew | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);

  const empty: Partial<WorkCrew> = {
    name: "",
    work_type: "roofer",
    available_from: today,
    available_to: addDays(today, 365),
    work_days: ["po", "ut", "st", "ct", "pa"],
    absent_dates: [],
    active: true,
  };

  const [form, setForm] = useState<Partial<WorkCrew>>(empty);

  const openAdd = () => {
    setForm({ ...empty });
    setEditing(null);
    setShowForm(true);
  };

  const openEdit = (c: WorkCrew) => {
    setForm({ ...c });
    setEditing(c);
    setShowForm(true);
  };

  const handleSubmit = async () => {
    setBusy(true);
    try {
      if (editing) {
        await onUpdate(editing.id, form);
      } else {
        await onAdd(form);
      }
      setShowForm(false);
    } finally {
      setBusy(false);
    }
  };

  const toggleWorkDay = (day: string) => {
    setForm((f) => ({
      ...f,
      work_days: (f.work_days ?? []).includes(day)
        ? (f.work_days ?? []).filter((d) => d !== day)
        : [...(f.work_days ?? []), day],
    }));
  };

  const addAbsentDate = () => {
    setForm((f) => ({ ...f, absent_dates: [...(f.absent_dates ?? []), ""] }));
  };

  const setAbsentDate = (idx: number, val: string) => {
    setForm((f) => ({
      ...f,
      absent_dates: (f.absent_dates ?? []).map((d, i) => (i === idx ? val : d)),
    }));
  };

  const removeAbsentDate = (idx: number) => {
    setForm((f) => ({
      ...f,
      absent_dates: (f.absent_dates ?? []).filter((_, i) => i !== idx),
    }));
  };

  if (!showForm) {
    return (
      <div className="card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm text-navy">Správa čteta</h3>
          <button onClick={openAdd} className="btn-secondary text-xs">
            + Přidat četu
          </button>
        </div>
        {crews.length === 0 && (
          <p className="text-xs text-slateMuted p-2">Žádné čety k zobrazení.</p>
        )}
        {crews.map((c) => (
          <div key={c.id} className="border border-slate-200 rounded-lg p-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-navy">{c.name}</p>
                <p className="text-xs text-slateMuted">
                  {WORK_TYPE_LABEL[c.work_type] ?? c.work_type} ·{" "}
                  {c.available_from} → {c.available_to}
                </p>
              </div>
              <button
                onClick={() => openEdit(c)}
                className="text-xs text-antelonGreen hover:underline"
              >
                Upravit
              </button>
            </div>
            <div className="flex items-center gap-1 mt-1.5">
              {["po", "ut", "st", "ct", "pa"].map((d) => (
                <span
                  key={d}
                  className={`text-[10px] px-1.5 py-0.5 rounded ${c.work_days.includes(d) ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-400"}`}
                >
                  {WORK_DAY_MAP[d] ?? d}
                </span>
              ))}
            </div>
            {c.absent_dates.length > 0 && (
              <p className="text-[10px] text-red-400 mt-1">
                Výjimky: {c.absent_dates.join(", ")}
              </p>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="card p-4 space-y-3" data-testid="crew-editor">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-navy">
          {editing ? `Upravit: ${editing.name}` : "Nová četa"}
        </h3>
        <button onClick={() => setShowForm(false)} className="text-xs text-slateMuted hover:underline">
          Zrušit
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col text-xs">
          Název
          <input
            type="text"
            value={form.name ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="mt-1 border border-slate-200 rounded px-2 py-1.5 text-sm"
          />
        </label>
        <label className="flex flex-col text-xs">
          Typ
          <select
            value={form.work_type ?? "roofer"}
            onChange={(e) => setForm((f) => ({ ...f, work_type: e.target.value }))}
            className="mt-1 border border-slate-200 rounded px-2 py-1.5 text-sm"
          >
            <option value="roofer">Montáž</option>
            <option value="electrician">Elektro</option>
            <option value="other">Ostatní</option>
          </select>
        </label>
        <label className="flex flex-col text-xs">
          Od
          <input
            type="date"
            value={form.available_from ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, available_from: e.target.value }))}
            className="mt-1 border border-slate-200 rounded px-2 py-1.5 text-sm"
          />
        </label>
        <label className="flex flex-col text-xs">
          Do
          <input
            type="date"
            value={form.available_to ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, available_to: e.target.value }))}
            className="mt-1 border border-slate-200 rounded px-2 py-1.5 text-sm"
          />
        </label>
      </div>

      <div className="text-xs">
        <p className="font-medium mb-1">Pracovní dny:</p>
        <div className="flex gap-2">
          {["po", "ut", "st", "ct", "pa"].map((d) => (
            <label key={d} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={(form.work_days ?? []).includes(d)}
                onChange={() => toggleWorkDay(d)}
              />
              {WORK_DAY_MAP[d]}
            </label>
          ))}
        </div>
      </div>

      <div className="text-xs">
        <div className="flex items-center justify-between mb-1">
          <p className="font-medium">Výjimky (absence):</p>
          <button onClick={addAbsentDate} className="text-antelonGreen hover:underline">
            + Přidat
          </button>
        </div>
        {(form.absent_dates ?? []).map((d, idx) => (
          <div key={idx} className="flex items-center gap-1 mb-1">
            <input
              type="date"
              value={d}
              onChange={(e) => setAbsentDate(idx, e.target.value)}
              className="border border-slate-200 rounded px-2 py-1 flex-1"
            />
            <button
              onClick={() => removeAbsentDate(idx)}
              className="text-red-400 hover:text-red-600 px-1"
            >
              ×
            </button>
          </div>
        ))}
        {(form.absent_dates ?? []).length === 0 && (
          <p className="text-slate-400">Žádné výjimky.</p>
        )}
      </div>

      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={form.active ?? true}
          onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
        />
        Aktivní
      </label>

      <div className="flex justify-end gap-2">
        <button onClick={() => setShowForm(false)} className="btn-secondary text-sm">
          Zrušit
        </button>
        <button
          onClick={handleSubmit}
          disabled={busy || !form.name}
          className="btn-navy text-sm disabled:opacity-50"
        >
          {busy ? "Ukládám..." : editing ? "Uložit" : "Přidat"}
        </button>
      </div>
    </div>
  );
}

// ---------- Hlavní komponenta ----------

export default function Planovani() {
  const { user } = useAuth();
  const isAdmin = hasAnyRole(user, ["admin", "antelon"]);

  const [overviewData, setOverviewData] = useState<PlanningOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [crews, setCrews] = useState<WorkCrew[]>([]);
  const [sim, setSim] = useState<SimulateResponse | null>(null);
  const [addRoofer, setAddRoofer] = useState(false);
  const [addElectrician, setAddElectrician] = useState(false);
  const [simPending, setSimPending] = useState(false);

  // Přehled se načte jednou — plán se kotví na reálném „dnes“.
  // overviewData záměrně NENÍ v deps: jinak by každý příchod dat spustil
  // efekt znovu a stránka by do nekonečna re-fetchovala.
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const data = await getOverview(today, addDays(today, GANTT_DAYS));
      setOverviewData(data);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e instanceof Error ? e.message : "Chyba načtení");
      setError(m);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Čety se načtou, až je pozná role — user se v AuthContext načítá async,
  // takže se toto musí spustit zvlášť (a bez re-fetchu přehledu).
  useEffect(() => {
    if (!isAdmin) return;
    listCrews().then(setCrews).catch(() => {});
  }, [isAdmin]);

  const refreshCrews = useCallback(() => {
    listCrews().then(setCrews).catch(() => {});
  }, []);

  // What-if: call simulate when toggles change
  useEffect(() => {
    if (!overviewData) return;
    const add: Record<string, number> = {};
    if (addRoofer) add["roofer"] = 1;
    if (addElectrician) add["electrician"] = 1;
    if (Object.keys(add).length === 0) {
      setSim(null);
      return;
    }
    (async () => {
      setSimPending(true);
      try {
        const s = await simulate({ add_crews: add });
        setSim(s);
      } catch {
        // ignore
      } finally {
        setSimPending(false);
      }
    })();
  }, [addRoofer, addElectrician, overviewData]);

  const handleCrewAdd = async (body: Partial<WorkCrew>) => {
    await createCrew(body);
    load();
    refreshCrews();
  };

  const handleCrewUpdate = async (id: number, body: Partial<WorkCrew>) => {
    await updateCrew(id, body);
    load();
    refreshCrews();
  };

   return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-navy">Plánování montáže a elektro</h1>
        <p className="text-sm text-slateMuted mt-0.5">
          Přehled pracovních čteta, Ganttův diagram a simulace co-kdyby
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded">
          {error}
        </div>
      )}

      {loading ? (
        <div className="animate-pulse space-y-3">
          <div className="h-10 bg-slate-200 rounded" />
          <div className="h-64 bg-slate-200 rounded" />
          <div className="h-64 bg-slate-200 rounded" />
        </div>
      ) : overviewData ? (
        <>
          {/* Přehled — KPI karty */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="kpi-card border-l-emerald-500">
              <p className="text-xs text-slateMuted uppercase">Dnes</p>
              <p className="text-lg font-bold text-navy">
                {formatDate(overviewData.today)}
              </p>
            </div>
            <div className="kpi-card border-l-blue-500">
              <p className="text-xs text-slateMuted uppercase">Vše hotovo do</p>
              {(sim ?? overviewData).makespan ? (
                <p className="text-lg font-bold text-navy">{formatDate((sim ?? overviewData).makespan!)}</p>
              ) : (
                <>
                  <p className="text-lg font-bold text-slate-400">—</p>
                  <p className="text-xs text-slateMuted">bez čteta</p>
                </>
              )}
            </div>
            {sim && overviewData.makespan && sim.makespan && (
              <div className="kpi-card border-l-amber-500">
                <p className="text-xs text-slateMuted uppercase">Simulace vs základní</p>
                <p className="text-lg font-bold text-amber-600">
                  {daysBetween(overviewData.makespan, sim.makespan) >= 0
                    ? `+${daysBetween(overviewData.makespan, sim.makespan)} dnů`
                    : `${daysBetween(overviewData.makespan, sim.makespan)} dnů`}
                </p>
                <p className="text-xs text-slateMuted">
                  hotovo {formatDate(sim.makespan)}
                </p>
              </div>
            )}
            <div className="kpi-card border-l-slate-400">
              <p className="text-xs text-slateMuted uppercase">Svátky v období</p>
              <p className="text-lg font-bold text-navy">
                {overviewData.holidays_in_range.length}
              </p>
            </div>
          </div>

          {/* Gantt — data z sim nebo overview */}
          <div>
            <h2 className="text-lg font-semibold text-navy mb-2">Ganttův diagram</h2>
            <GanttChart overview={overviewData} sim={sim} />
          </div>

          {/* Kalendář */}
          <div>
            <h2 className="text-lg font-semibold text-navy mb-2">Kalendář</h2>
            <CalendarMonth overview={overviewData} sim={sim} />
          </div>

          {/* Panel čteta — jen admin/antelon */}
          {isAdmin && (
            <CrewEditor
              crews={crews}
              onAdd={handleCrewAdd}
              onUpdate={handleCrewUpdate}
              today={overviewData.today}
            />
          )}
        </>
      ) : null}

      {/* What-if toggle */}
      {overviewData && (
        <div className="card p-3">
          <h3 className="font-semibold text-sm text-navy mb-2">Co-kdyby simulace</h3>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={addRoofer}
                onChange={(e) => setAddRoofer(e.target.checked)}
                data-testid="what-if-roofer"
                className="rounded border-slate-300"
              />
              +1 montáž
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={addElectrician}
                onChange={(e) => setAddElectrician(e.target.checked)}
                data-testid="what-if-electrician"
                className="rounded border-slate-300"
              />
              +1 elektro
            </label>
            {simPending && (
              <span className="text-xs text-slateMuted">Volání API…</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
