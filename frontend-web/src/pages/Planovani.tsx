import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  inspector: "Inspekce",
};

const WORK_TYPE_COLORS: Record<string, string> = {
  roofer: "bg-emerald-500",
  electrician: "bg-sky-500",
};

function workTypeColor(wt: string): string {
  return WORK_TYPE_COLORS[wt] ?? "bg-amber-400";
}

// Počet čteta podle typu → „3 Montáž · 2 Elektro“ (souhrn simulace)
function crewSummary(crews: { work_type: string }[]): string {
  const counts = new Map<string, number>();
  for (const c of crews) counts.set(c.work_type, (counts.get(c.work_type) ?? 0) + 1);
  return Array.from(counts.entries())
    .map(([wt, n]) => `${n} ${WORK_TYPE_LABEL[wt] ?? wt}`)
    .join(" · ");
}

// ---------- Gantt data helpers ----------

const GANTT_DAYS = 90;

// Rozsah Gantu: z dneška do max(today+90d, makespan+7d) — aby se daly
// dooboru vidět i delší plány.
function ganttEnd(today: string, makespan: string | null): string {
  const base = addDays(today, GANTT_DAYS);
  return makespan && makespan > base ? addDays(makespan, 7) : base;
}

function buildDayLabels(today: string, end: string) {
  const days: { date: string; month: number; dayInMonth: number }[] = [];
  for (let d = new Date(today); d.toISOString().slice(0, 10) <= end; d.setDate(d.getDate() + 1)) {
    days.push({
      date: d.toISOString().slice(0, 10),
      month: d.getMonth(),
      dayInMonth: d.getDate(),
    });
  }
  return days;
}

type GanttZoom = "day" | "week" | "month";

interface GanttCol {
  key: string;
  label: string;
  start: number; // index prvního dne (do days)
  end: number;   // index posledního dne (do days)
  width: number; // px
}

function isoWeekStart(date: string): string {
  const d = new Date(date);
  const dow = (d.getDay() + 6) % 7; // 0 = pondělí
  d.setDate(d.getDate() - dow);
  return d.toISOString().slice(0, 10);
}

const MONTH_NAMES = [
  "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
  "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
];

function buildGanttCols(
  days: { date: string; month: number; dayInMonth: number }[],
  zoom: GanttZoom,
): GanttCol[] {
  if (zoom === "day") {
    return days.map((d, i) => ({
      key: d.date,
      label: String(d.dayInMonth),
      start: i,
      end: i,
      width: 40,
    }));
  }
  const cols: GanttCol[] = [];
  let i = 0;
  while (i < days.length) {
    let end = i;
    let key: string;
    if (zoom === "week") {
      key = isoWeekStart(days[i].date);
      while (end + 1 < days.length && isoWeekStart(days[end + 1].date) === key) end++;
      const ds = new Date(days[i].date);
      const de = new Date(days[end].date);
      const label =
        days[i].date === days[end].date
          ? `${ds.getDate()}.${ds.getMonth() + 1}.`
          : ds.getMonth() === de.getMonth()
            ? `${ds.getDate()}.–${de.getDate()}.${ds.getMonth() + 1}.`
            : `${ds.getDate()}.${ds.getMonth() + 1}.–${de.getDate()}.${de.getMonth() + 1}.`;
      cols.push({ key, label, start: i, end, width: 140 });
    } else {
      key = days[i].date.slice(0, 7); // YYYY-MM
      while (end + 1 < days.length && days[end + 1].date.slice(0, 7) === key) end++;
      const d = new Date(days[i].date);
      cols.push({
        key,
        label: `${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`,
        start: i,
        end,
        width: 130,
      });
    }
    i = end + 1;
  }
  return cols;
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
  const days = useMemo(
    () => buildDayLabels(overview.today, ganttEnd(overview.today, overview.makespan)),
    [overview.today, overview.makespan],
  );
  const dayIndex = useMemo(() => {
    const m = new Map<string, number>();
    days.forEach((d, i) => m.set(d.date, i));
    return (t: string | null | undefined) => (t ? m.get(t) ?? -1 : -1);
  }, [days]);
  const holidays = overview.holidays_in_range;
  const today = overview.today;

  const [zoom, setZoom] = useState<GanttZoom>("day");
  const [jumpDate, setJumpDate] = useState(today);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Sloupce pro aktuální zoom + kumulativní levé okraje
  const cols = useMemo(() => buildGanttCols(days, zoom), [days, zoom]);
  const colLeft = useMemo(() => {
    const left: number[] = [0];
    for (let i = 0; i < cols.length; i++) left.push(left[i] + cols[i].width);
    return left;
  }, [cols]);
  const colOf = useMemo(() => {
    const m = new Map<number, number>();
    cols.forEach((c, i) => {
      for (let d = c.start; d <= c.end; d++) m.set(d, i);
    });
    return (dayIdx: number) => m.get(dayIdx) ?? -1;
  }, [cols]);

  // Virtuální čety ze simulace → pruhovaný rámec v Gantu
  const virtualCrews = useMemo(
    () => new Set((sim?.crews ?? []).filter((c) => c.virtual).map((c) => c.name)),
    [sim],
  );

  // Posun na sloupec obsahující dané datum (ofset pro sticky sloupec)
  const scrollToDay = (dateStr: string) => {
    const idx = dayIndex(dateStr);
    if (idx < 0) return;
    const ci = colOf(idx);
    if (ci < 0) return;
    scrollRef.current?.scrollTo({
      left: Math.max(colLeft[ci] - 176, 0),
      behavior: "smooth",
    });
  };

  // Horní řada: meze měsíců (dny/týdny) nebo let (měsíce)
  const topSpans: { key: string; label: string; width: number }[] = [];
  for (const c of cols) {
    const d = days[c.start];
    const key = zoom === "month" ? d.date.slice(0, 4) : `${d.date.slice(0, 4)}-${d.month}`;
    const label = zoom === "month" ? d.date.slice(0, 4) : MONTH_NAMES[d.month];
    const last = topSpans[topSpans.length - 1];
    if (last && last.key === key) last.width += c.width;
    else topSpans.push({ key, label, width: c.width });
  }

  const totalWidth = colLeft[cols.length];

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
    <div ref={scrollRef} className="card overflow-x-auto" data-testid="gantt-chart">
      {/* Zoom + skok do období */}
      <div className="flex flex-wrap items-center gap-2 p-2 border-b border-slate-200">
        <div className="flex rounded overflow-hidden border border-slate-300">
          {(
            [
              ["day", "Dny"],
              ["week", "Týdny"],
              ["month", "Měsíce"],
            ] as const
          ).map(([z, name]) => (
            <button
              key={z}
              onClick={() => setZoom(z)}
              className={`px-2.5 py-1 text-xs ${
                zoom === z ? "bg-navy text-white" : "bg-white text-slateMuted hover:bg-slate-50"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 ml-auto">
          <input
            type="date"
            value={jumpDate}
            min={days[0]?.date}
            max={days[days.length - 1]?.date}
            onChange={(e) => setJumpDate(e.target.value)}
            data-testid="gantt-jump-date"
            className="text-xs border border-slate-300 rounded px-1.5 py-1"
          />
          <button
            onClick={() => scrollToDay(jumpDate)}
            data-testid="gantt-jump"
            className="text-xs px-2 py-1 rounded bg-navy text-white hover:opacity-90"
          >
            Jít
          </button>
          <button
            onClick={() => scrollToDay(today)}
            className="text-xs px-2 py-1 rounded border border-slate-300 text-slateMuted hover:bg-slate-50"
          >
            Dnes
          </button>
        </div>
      </div>
      <div style={{ width: totalWidth }}>
        {/* Header: měsíce/roky + sloupce */}
        <div className="flex border-b border-slate-200">
          <div className="sticky left-0 z-20 bg-white border-r border-slate-200 w-48 min-w-[12rem] flex-shrink-0 p-2 text-xs font-semibold text-slateMuted uppercase">
            Zakázka
          </div>
          <div>
            {/* Horní řada: měsíce (při zoomu na měsíce roky) */}
            <div className="flex border-b border-slate-100">
              {topSpans.map((s) => (
                <div
                  key={s.key}
                  className="text-center text-[10px] font-semibold text-slateMuted py-0.5 border-r border-slate-50 bg-slate-50"
                  style={{ width: s.width }}
                >
                  {s.label}
                </div>
              ))}
            </div>
            {/* Sloupce */}
            <div className="flex">
              {cols.map((c) => {
                const d = days[c.start];
                const wknd = zoom === "day" && isWeekend(d.date);
                const hol = zoom === "day" && holidays.includes(d.date);
                const isToday = d.date === today;
                return (
                  <div
                    key={c.key}
                    className={`h-5 text-[10px] text-center leading-5 border-r border-slate-100 ${
                      wknd || hol ? "bg-slate-100 text-slate-400" : "text-slateMuted"
                    } ${isToday ? "bg-emerald-50 text-emerald-700 font-bold" : ""}`}
                    title={zoom === "day" ? d.date : undefined}
                  >
                    {c.label}
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
              <div className="relative flex-shrink-0" style={{ height: 32, width: totalWidth }}>
                {cols.map((c, i) => (
                  <div
                    key={c.key}
                    className="absolute top-0 bottom-0 border-r border-slate-50"
                    style={{ left: colLeft[i] }}
                  />
                ))}
                {/* Today line */}
                {(() => {
                  const idx = dayIndex(today);
                  const ci = idx >= 0 ? colOf(idx) : -1;
                  if (ci < 0) return null;
                  const c = cols[ci];
                  const frac = (idx - c.start) / (c.end - c.start + 1);
                  return (
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-emerald-500 z-10"
                      style={{ left: colLeft[ci] + frac * c.width }}
                      title={`Dnes (${today})`}
                    />
                  );
                })()}
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
                  const ci = colOf(si);
                  const cj = colOf(ei);
                  const left = colLeft[ci] + 1;
                  const width = Math.max(colLeft[cj + 1] - colLeft[ci] - 2, 8);
                  const colorClass = workTypeColor(item.work_type);
                  const isVirtual = !!item.crew_name && virtualCrews.has(item.crew_name);
                  const showText = width >= 60;
                  return (
                    <div
                      key={`${item.step_code}-${idx}`}
                      className={`absolute top-1 h-6 rounded flex items-center px-1.5 text-[9px] text-white truncate font-medium z-5 ${colorClass} ${!isF ? "opacity-50" : ""} ${isVirtual ? "border-2 border-dashed border-white/80" : ""}`}
                      style={{ left, width }}
                      title={`${item.step_name}: ${item.start}${item.end ? ` → ${item.end}` : ""}${item.crew_name ? `\nČeta: ${item.crew_name}${isVirtual ? " (virtuální)" : ""}` : ""}`}
                    >
                      {showText && item.step_name}
                      {showText && item.crew_name && (
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
    const days = buildDayLabels(
      overview.today,
      ganttEnd(overview.today, overview.makespan),
    );
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
  }, [items, overview.today, overview.makespan]);

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
  // What-if: počet dodatečných četa podle typu (0 = nic nepřidat)
  const [extraCrews, setExtraCrews] = useState<Record<string, number>>({});
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

  // Typy čteta pro what-if: unie typů z čteta i položek plánu
  const workTypes = useMemo(() => {
    if (!overviewData) return [];
    const set = new Set<string>();
    for (const c of overviewData.crews) set.add(c.work_type);
    for (const i of overviewData.items) set.add(i.work_type);
    const known = ["roofer", "electrician", "inspector"];
    return [
      ...known.filter((k) => set.has(k)),
      ...Array.from(set)
        .filter((t) => !known.includes(t))
        .sort(),
    ];
  }, [overviewData]);

  // What-if: volá simulate, když se změní počty čteta
  useEffect(() => {
    if (!overviewData) return;
    const add: Record<string, number> = {};
    for (const [wt, n] of Object.entries(extraCrews)) {
      if (n > 0) add[wt] = n;
    }
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
  }, [extraCrews, overviewData]);

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
                {sim.crews.length > 0 && (
                  <p className="text-xs text-slateMuted mt-1">
                    Čety: <span>{crewSummary(sim.crews)}</span>
                  </p>
                )}
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

      {/* What-if — počet dodatečných čteta podle typu */}
      {overviewData && (
        <div className="card p-3">
          <h3 className="font-semibold text-sm text-navy mb-2">Co-kdyby simulace</h3>
          <div className="flex flex-wrap items-center gap-4">
            {workTypes.map((wt) => (
              <label key={wt} className="flex items-center gap-2 text-sm">
                {WORK_TYPE_LABEL[wt] ?? wt}
                <input
                  type="number"
                  min={0}
                  max={5}
                  step={1}
                  value={extraCrews[wt] ?? 0}
                  onChange={(e) => {
                    const v = Math.max(0, Math.min(5, Number(e.target.value) || 0));
                    setExtraCrews((prev) => ({ ...prev, [wt]: v }));
                  }}
                  data-testid={`what-if-${wt}`}
                  className="w-14 rounded border border-slate-300 px-1.5 py-0.5 text-sm"
                />
              </label>
            ))}
            {simPending && (
              <span className="text-xs text-slateMuted">Volání API…</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
