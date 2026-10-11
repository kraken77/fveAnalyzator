import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { hasAnyRole, useAuth } from "../context/AuthContext";
import { BOARD_PHASES, mainPhaseOf, type BoardPhaseKey } from "../constants/pipelinePhases";
import {
  addInvoiceItem,
  addTimeEntry,
  adminListUsers,
  getInvoiceItems,
  getPipeline,
  getProjectEconomy,
  getTimeEntries,
  getTimeSummary,
  monteriCsvUrl,
  reviewAI,
  runAI,
  setInvoiceStatus,
  transitionStep,
} from "../api/pipeline";
import type {
  InvoiceItem,
  PipelineStep,
  PipelineView,
  ProjectEconomy,
  TimeEntry,
  TimeSummary,
} from "../types";

type TabId = "pipeline" | "times" | "invoices" | "economy" | "events";

const STATUS_BADGE: Record<string, string> = {
  done: "bg-emerald-100 text-emerald-800",
  in_progress: "bg-amber-100 text-amber-800",
  planned: "bg-sky-100 text-sky-800",
  skipped: "bg-slate-100 text-slate-500",
  cancelled: "bg-slate-200 text-slate-500",
  not_started: "bg-white text-slate-500 border border-slate-200",
};

const ACTION_LABEL: Record<string, string> = {
  plan: "Plánovat",
  begin: "Začít",
  complete: "Dokončit",
  sent: "Odeslat",
  sign: "Podepsat",
  skip: "Přeskočit",
  revert: "Vrátit",
  cancel: "Zrušit",
  assign: "Přiřadit",
  run_ai: "Spustit AI",
};

const ACTION_COLOR: Record<string, string> = {
  plan: "btn-secondary",
  begin: "btn-primary",
  complete: "btn-primary",
  sent: "btn-primary",
  sign: "btn-navy",
  skip: "btn-secondary",
  revert: "btn-secondary",
  cancel: "btn-secondary",
  assign: "btn-secondary",
  run_ai: "btn-navy",
};

const PHASE_LABEL: Record<string, string> = {
  lead: "Lead",
  priprava: "Příprava",
  sledovani: "Sledování",
  smlouva: "Smlouva",
  finance: "Finance",
  pripojeni: "Připojení",
  dotace: "Dotace & půjčka",
  realizace: "Realizace",
  predani: "Předání",
  revize: "Revize",
  pretoky: "Přetoky",
  final: "Finální",
  servis: "Servis & správa",
};

export default function PipelineDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const pid = id ?? "";
  const isAdmin = hasAnyRole(user, ["admin"]);

  const [view, setView] = useState<PipelineView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [active, setActive] = useState<TabId>("pipeline");

  // Sub-taby fází: single source of truth je URL (?phase=…&stepId=…),
  // aby deep-link z dispečinku fungoval bez dalšího stavu.
  const [searchParams, setSearchParams] = useSearchParams();
  const phaseParam = searchParams.get("phase");
  const activePhase = BOARD_PHASES.find((p) => p.key === phaseParam)?.key ?? null;
  // stepId musí být číslo – jinak hrozí SyntaxError v querySelectoru
  const stepParam = searchParams.get("stepId");
  const targetStepId = stepParam && /^\d+$/.test(stepParam) ? stepParam : null;

  const [flashStepId, setFlashStepId] = useState<string | null>(null);
  // deep-link (scroll + blik) proběhne jednou za návštěvu daného kroku,
  // aby se neopakoval po každém refresh()
  const deepLinkDoneForRef = useRef<string | null>(null);
  const flashTimerRef = useRef<number | null>(null);

  const setPhaseTab = (key: BoardPhaseKey | null) => {
    const next = new URLSearchParams(searchParams);
    if (key) next.set("phase", key);
    else next.delete("phase");
    next.delete("stepId");
    setSearchParams(next, { replace: true });
  };

  // inline plan form
  const [planStepId, setPlanStepId] = useState<string | number | null>(null);
  const [planDate, setPlanDate] = useState("");
  const [assignedUserId, setAssignedUserId] = useState<string>("");
  const [note, setNote] = useState("");
  const [users, setUsers] = useState<Array<{ id: number | string; email: string; role: string }>>([]);

  // times
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [summary, setSummary] = useState<TimeSummary | null>(null);
  const [teStep, setTeStep] = useState<string>("");
  const [teMinutes, setTeMinutes] = useState<string>("30");
  const [teKind, setTeKind] = useState<"admin" | "work">("admin");
  const [teDate, setTeDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [teNote, setTeNote] = useState("");

  // invoices
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [invType, setInvType] = useState("zaloha");
  const [invDesc, setInvDesc] = useState("");
  const [invAmount, setInvAmount] = useState("0");

  // economy
  const [economy, setEconomy] = useState<ProjectEconomy | null>(null);

  const refresh = useCallback(async () => {
    if (!pid) return;
    setLoading(true);
    setError(null);
    try {
      const v = await getPipeline(pid);
      setView(v);
      await Promise.all([
        getTimeEntries(pid).then(setEntries).catch(() => undefined),
        getTimeSummary(pid).then(setSummary).catch(() => undefined),
        getInvoiceItems(pid).then(setInvoices).catch(() => undefined),
        getProjectEconomy(pid).then(setEconomy).catch(() => undefined),
      ]);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : "Chyba načtení");
      setError(m);
    } finally {
      setLoading(false);
    }
  }, [pid]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Deep-link: scroll + 3 s zvýraznění cílového kroku, počítáno od načtení
  // dat. Proběhne jednou za návštěvu kroku – refresh() po akcích nesmí scroll
  // zopakovat (stránka by "skákala" po každém kliknutí).
  useEffect(() => {
    if (!view || !targetStepId) return;
    if (deepLinkDoneForRef.current === targetStepId) return;
    deepLinkDoneForRef.current = targetStepId;
    setFlashStepId(targetStepId);
    document
      .querySelector(`[data-step-id="${targetStepId}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    // timer žije i při dalších bězích efektu (refresh), klidí ho jen unmount;
    // při změně stepId ve stejné mountu přednost nenecháváme starému
    if (flashTimerRef.current !== null) window.clearTimeout(flashTimerRef.current);
    flashTimerRef.current = window.setTimeout(() => setFlashStepId(null), 3000);
  }, [view, targetStepId]);

  useEffect(
    () => () => {
      if (flashTimerRef.current !== null) window.clearTimeout(flashTimerRef.current);
    },
    [],
  );

  useEffect(() => {
    if (isAdmin) {
      adminListUsers()
        .then(setUsers)
        .catch(() => setUsers([]));
    }
  }, [isAdmin]);

  const resetPlan = () => {
    setPlanStepId(null);
    setPlanDate("");
    setAssignedUserId("");
    setNote("");
  };

  const doAction = async (step: PipelineStep, action: string) => {
    setBusy(`${step.id}:${action}`);
    setMsg(null);
    try {
      await transitionStep(pid, step.id, {
        action,
        plan_date: planDate ? new Date(planDate).toISOString() : null,
        assigned_user_id: assignedUserId ? Number(assignedUserId) : null,
        note: note || null,
      });
      resetPlan();
      setMsg(`Krok „${step.name}“ — ${ACTION_LABEL[action] ?? action} OK`);
      await refresh();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : "Akce selhala");
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  const handleRunAi = async (step: PipelineStep) => {
    setBusy(`ai:${step.id}`);
    setMsg(null);
    try {
      const res = await runAI(pid, step.id, "manual");
      setMsg(`AI krok spuštěn (výsledek #${res.id}) — čeká na schválení`);
      await refresh();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "AI krok selhal";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  const handleReview = async (step: PipelineStep, resultId: number | string, approved: boolean) => {
    let noteText: string | undefined;
    if (!approved) {
      noteText = window.prompt("Důvod zamítnutí:") ?? undefined;
    }
    setBusy(`review:${step.id}`);
    try {
      await reviewAI(pid, step.id, resultId, approved, noteText);
      setMsg(approved ? "AI výstup schválen" : "AI výstup zamítnut");
      await refresh();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Hodnocení selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  const handleAddTime = async () => {
    if (!pid) return;
    setBusy("time");
    setMsg(null);
    try {
      await addTimeEntry(pid, {
        step_id: teStep ? Number(teStep) : null,
        minutes: Number(teMinutes) || 0,
        kind: teKind,
        work_date: teDate,
        note: teNote || undefined,
      });
      setMsg("Čas zapsán");
      setTeMinutes("30");
      await Promise.all([
        getTimeEntries(pid).then(setEntries),
        getTimeSummary(pid).then(setSummary),
        refresh(),
      ]);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Zápis času selhal";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  const handleAddInvoice = async () => {
    if (!pid) return;
    setBusy("inv");
    setMsg(null);
    try {
      await addInvoiceItem(pid, {
        doc_type: invType,
        description: invDesc || undefined,
        amount_czk: Number(invAmount) || 0,
      });
      setMsg("Fakturační položka přidána");
      setInvDesc("");
      setInvAmount("0");
      await getInvoiceItems(pid).then(setInvoices);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Přidání selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  const handleIssue = async (item: InvoiceItem) => {
    if (!pid) return;
    setBusy(`issue:${item.id}`);
    try {
      const res = await setInvoiceStatus(pid, item.id, "issued");
      setMsg(`Vystaveno — ${res.doc_number ?? ""}`);
      await getInvoiceItems(pid).then(setInvoices);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Vystavení selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  const phases = useMemo(() => {
    if (!view) return [];
    const map = new Map<string, PipelineStep[]>();
    for (const s of view.steps) {
      if (s.hidden) continue;
      const arr = map.get(s.phase) ?? [];
      arr.push(s);
      map.set(s.phase, arr);
    }
    return Array.from(map.entries()).sort((a, b) => {
      const oa = view.steps.find((x) => x.phase === a[0])?.order ?? 0;
      const ob = view.steps.find((x) => x.phase === b[0])?.order ?? 0;
      return oa - ob;
    });
  }, [view]);

  const visiblePhases = activePhase
    ? phases.filter(([phase]) => mainPhaseOf(phase) === activePhase)
    : phases;

  const formatAiOutput = (out: Record<string, unknown> | undefined): string => {
    if (!out) return "";
    const pick = (k: string) => {
      const v = out[k];
      if (v === undefined || v === null) return null;
      if (typeof v === "number") return v.toLocaleString("cs-CZ");
      if (typeof v === "string") return v;
      return JSON.stringify(v);
    };
    const parts: string[] = [];
    const keys = ["kwp", "doporuceno_kwh", "samospotreba_pct", "castka_czk", "rocni_uspora_czk", "eligible", "amount_czk", "npv_czk", "roi_years", "pdf_version_id"];
    for (const k of keys) {
      const v = pick(k);
      if (v !== null) {
        parts.push(`${k}=${v}`);
      }
    }
    return parts.join("  ");
  };

  if (loading && !view) {
    return <div className="animate-pulse space-y-3"><div className="h-8 bg-slate-200 rounded w-1/3" /><div className="h-64 bg-slate-200 rounded" /></div>;
  }

  if (error && !view) {
    return (
      <div className="card p-8 text-center border-l-4 border-l-red-400">
        <p className="text-red-700">{error}</p>
        <Link to="/dispecink" className="btn-secondary mt-4 inline-block">Zpět na dispečink</Link>
      </div>
    );
  }

  if (!view) return null;

  const readySteps = view.steps.filter((s) => !s.hidden);

  return (
    <div className="space-y-5">
      <div>
        <Link to="/dispecink" className="text-xs text-slateMuted hover:text-navy">← Zpět na dispečink</Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold text-navy">{view.project.name}</h1>
            <p className="text-sm text-slateMuted">
              {view.project.customer_name || "—"} • typ: {view.project.type || "—"} • ID {String(view.project.id)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {view.template && (
              <span className="text-xs bg-slate-100 border border-slate-200 rounded px-2 py-1">
                {view.template.name}
              </span>
            )}
            <span className={`text-xs font-semibold px-2 py-1 rounded ${view.project.status === "cancelled" ? "bg-slate-200 text-slate-600" : "bg-emerald-100 text-emerald-800"}`}>
              {view.project.status}
            </span>
          </div>
        </div>
      </div>

      {msg && (
        <div className={`px-3 py-2 rounded text-sm flex justify-between ${msg.startsWith("Chyba") ? "bg-red-50 border border-red-200 text-red-700" : "bg-emerald-50 border border-emerald-200 text-emerald-800"}`}>
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold ml-4">×</button>
        </div>
      )}

      {/* tabs */}
      <div className="border-b border-slate-200 overflow-x-auto">
        <div className="flex gap-1 sm:gap-2">
          {([
            ["pipeline", "Pipeline"],
            ["times", "Časové výkazy"],
            ["invoices", "Fakturace"],
            ["economy", "Ekonomika"],
            ["events", "Historie"],
          ] as [TabId, string][]).map(([tid, label]) => (
            <button
              key={tid}
              onClick={() => setActive(tid)}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                active === tid ? "border-antelonGreen text-navy" : "border-transparent text-slateMuted hover:text-navy"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* PIPELINE TAB */}
      {active === "pipeline" && (
        <div className="space-y-5">
          <div className="flex items-center gap-4 text-xs text-slateMuted">
            <span>Hotovo: {view.steps.filter((s) => ["done", "signed", "skipped", "not_applicable"].includes(s.status)).length}/{readySteps.length}</span>
            <Link to={`/projects/${view.project.id}/materialy`} className="btn-secondary text-xs px-3 py-1.5">
              Materiály projektu →
            </Link>
          </div>

          {/* sub-taby fází (deep-link z dispečinku: ?phase=…&stepId=…) */}
          <div className="flex gap-1 flex-wrap" data-testid="phase-tabs">
            <button
              onClick={() => setPhaseTab(null)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition ${
                activePhase === null
                  ? "bg-slate-800 text-white border-slate-800"
                  : "bg-white text-slateMuted border-slate-200 hover:border-slate-400"
              }`}
            >
              Vše
            </button>
            {BOARD_PHASES.map((p) => (
              <button
                key={p.key}
                onClick={() => setPhaseTab(p.key)}
                className={`px-3 py-1.5 text-xs font-medium rounded-full border transition ${
                  activePhase === p.key
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-slateMuted border-slate-200 hover:border-slate-400"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {visiblePhases.length === 0 && (
            <div className="card p-6 text-center text-sm text-slateMuted">
              {activePhase ? "Žádné kroky v této fázi." : "Projekt zatím nemá žádné kroky."}
            </div>
          )}

          {visiblePhases.map(([phase, steps]) => (
            <div key={phase}>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slateMuted mb-2">
                {PHASE_LABEL[phase] ?? phase}
              </h2>
              <div className="space-y-2">
                {steps.map((s) => {
                  const ai = s.ai;
                  return (
                  <div
                    key={String(s.id)}
                    data-step-id={String(s.id)}
                    data-highlighted={flashStepId === String(s.id) ? "true" : undefined}
                    className={`card p-3 sm:p-4 ${
                      planStepId === s.id || flashStepId === String(s.id) ? "ring-2 ring-antelonGreen" : ""
                    }`}
                  >
                    <div className="flex flex-col lg:flex-row lg:items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_BADGE[s.status] ?? ""}`}>
                            {s.status}
                          </span>
                          <span className="font-medium text-navy">{s.name}</span>
                          <span className="text-xs text-slate-400 font-mono">{s.code}</span>
                          {s.auto_hook && (
                            <span className="text-[10px] bg-violet-50 text-violet-600 border border-violet-200 rounded px-1.5 py-0.5">
                              hook: {s.auto_hook}
                            </span>
                          )}
                          {s.parallel_group && (
                            <span className="text-[10px] bg-sky-50 text-sky-600 border border-sky-200 rounded px-1.5 py-0.5">
                              skupina {s.parallel_group}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slateMuted mt-1">
                          {s.plan_date ? `plán: ${new Date(s.plan_date).toLocaleDateString("cs-CZ")} ` : ""}
                          {s.assigned_user_id ? `• osoba #${s.assigned_user_id} ` : ""}
                          {s.est_admin_minutes ? `• admin ${s.est_admin_minutes} min ` : ""}
                          {s.est_work_minutes ? `• práce ${s.est_work_minutes} min ` : ""}
                          {(s.real_admin_minutes ?? 0) + (s.real_work_minutes ?? 0) > 0 && (
                            <span className="text-amber-700">• vykázáno {s.real_admin_minutes ?? 0}A/{s.real_work_minutes ?? 0}P</span>
                          )}
                        </p>
                        {s.note && <p className="text-xs text-slate-500 mt-1">📝 {s.note}</p>}
                      </div>

                      <div className="flex items-center gap-1.5 flex-wrap lg:justify-end">
                        {(s.can ?? []).map((action) => (
                          <button
                            key={action}
                            onClick={() => {
                              if (action === "plan" || action === "assign") {
                                if (planStepId === s.id && action === "assign") {
                                  doAction(s, "assign");
                                } else {
                                  setPlanStepId(s.id);
                                  setNote("");
                                }
                              } else if (action === "run_ai") {
                                handleRunAi(s);
                              } else {
                                const doIt = action === "cancel" ? window.confirm("Zrušit krok?") : true;
                                if (doIt) doAction(s, action);
                              }
                            }}
                            disabled={busy?.startsWith(`${s.id}:`) || busy === `ai:${s.id}`}
                            className={`${ACTION_COLOR[action] ?? "btn-secondary"} px-3 py-1.5 text-xs disabled:opacity-50`}
                          >
                            {busy?.startsWith(`${s.id}:`) ? "…" : ACTION_LABEL[action] ?? action}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* inline plan form */}
                    {planStepId === s.id && (
                      <div className="mt-3 pt-3 border-t border-slate-100 grid sm:grid-cols-4 gap-3">
                        <div>
                          <label className="text-xs font-semibold text-slateMuted">Plánované datum</label>
                          <input
                            type="date"
                            value={planDate}
                            onChange={(e) => setPlanDate(e.target.value)}
                            className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                          />
                        </div>
                        <div>
                          <label className="text-xs font-semibold text-slateMuted">Odpovědná osoba</label>
                          <select
                            value={assignedUserId}
                            onChange={(e) => setAssignedUserId(e.target.value)}
                            className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                          >
                            <option value="">—</option>
                            {users.map((u) => (
                              <option key={String(u.id)} value={String(u.id)}>
                                {u.email} ({u.role})
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="text-xs font-semibold text-slateMuted">Poznámka</label>
                          <input
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder="volitelné"
                            className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                          />
                        </div>
                        <div className="flex items-end gap-2">
                          <button
                            onClick={() => doAction(s, "plan")}
                            disabled={busy === `${s.id}:plan`}
                            className="btn-primary px-4 py-1.5 text-xs disabled:opacity-50"
                          >
                            Uložit plán
                          </button>
                          <button onClick={resetPlan} className="btn-secondary px-3 py-1.5 text-xs">
                            Zrušit
                          </button>
                        </div>
                      </div>
                    )}

                    {/* AI box */}
                    {(s.state_model === "ai" || s.ai) && (
                      <div className="mt-3 pt-3 border-t border-slate-100">
                        {ai ? (
                          <div className="text-sm bg-slate-50 border border-slate-200 rounded-lg p-3">
                            <div className="flex items-center justify-between flex-wrap gap-2">
                              <div>
                                <span className="text-xs font-semibold uppercase text-slateMuted">
                                  AI {ai.kind} — {ai.status}
                                </span>
                                <p className="text-navy mt-1 font-mono text-xs">{formatAiOutput(ai.output)}</p>
                              </div>
                              {ai.status === "draft" && (
                                <div className="flex items-center gap-2">
                                  <button
                                    onClick={() => handleReview(s, ai.id!, true)}
                                    disabled={busy === `review:${s.id}`}
                                    className="btn-primary px-3 py-1.5 text-xs disabled:opacity-50"
                                  >
                                    Schválit
                                  </button>
                                  <button
                                    onClick={() => handleReview(s, ai.id!, false)}
                                    disabled={busy === `review:${s.id}`}
                                    className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-50"
                                  >
                                    Zamítnout
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        ) : (
                          (s.can ?? []).includes("run_ai") && (
                            <button onClick={() => handleRunAi(s)} className="btn-navy px-3 py-1.5 text-xs">
                              ▶ Spustit AI ({s.code})
                            </button>
                          )
                        )}
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ČASOVÉ VÝKAZY */}
      {active === "times" && (
        <div className="space-y-5">
          <div className="card p-4 sm:p-5">
            <h3 className="font-semibold text-navy mb-3">Zapsat čas</h3>
            <div className="grid sm:grid-cols-5 gap-3">
              <div className="sm:col-span-1">
                <label className="text-xs font-semibold text-slateMuted">Krok</label>
                <select value={teStep} onChange={(e) => setTeStep(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm">
                  <option value="">(bez kroku)</option>
                  {readySteps.map((s) => (
                    <option key={String(s.id)} value={String(s.id)}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slateMuted">Minuty</label>
                <input type="number" min={1} value={teMinutes} onChange={(e) => setTeMinutes(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs font-semibold text-slateMuted">Typ</label>
                <select value={teKind} onChange={(e) => setTeKind(e.target.value as "admin" | "work")} className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm">
                  <option value="admin">admin</option>
                  <option value="work">práce (montér)</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slateMuted">Datum</label>
                <input type="date" value={teDate} onChange={(e) => setTeDate(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs font-semibold text-slateMuted">Poznámka</label>
                <input value={teNote} onChange={(e) => setTeNote(e.target.value)} placeholder="volitelné" className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm" />
              </div>
            </div>
            <button onClick={handleAddTime} disabled={busy === "time"} className="btn-primary mt-3 text-sm disabled:opacity-60">
              {busy === "time" ? "Zapisuji..." : "Zapsat čas"}
            </button>
            {isAdmin && (
              <div className="mt-3 flex items-center gap-2 text-sm">
                <span className="text-xs text-slateMuted">Výkaz montérů:</span>
                <a
                  href={monteriCsvUrl(`${new Date().getFullYear()}-01-01`, `${new Date().getFullYear()}-12-31`)}
                  className="btn-secondary px-3 py-1.5 text-xs"
                  data-testid="monteri-csv"
                >
                  stáhnout CSV (rok)
                </a>
              </div>
            )}
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <div className="card p-4">
              <h3 className="font-semibold text-navy mb-2">Záznamy ({entries.length})</h3>
              {entries.length === 0 ? (
                <p className="text-sm text-slateMuted">Zatím žádné výkazy.</p>
              ) : (
                <div className="divide-y text-sm max-h-96 overflow-auto">
                  {entries.map((te) => (
                    <div key={String(te.id)} className="py-2 flex justify-between gap-2">
                      <div>
                        <p className="font-medium text-navy">{te.step_name ?? "volný čas"}</p>
                        <p className="text-xs text-slateMuted">
                          {te.user_email} • {te.work_date ?? ""} {te.note ? `• ${te.note}` : ""}
                        </p>
                      </div>
                      <span className={`text-xs font-semibold self-center px-2 py-0.5 rounded ${te.kind === "work" ? "bg-antelonOrange/15 text-antelonOrange" : "bg-sky-100 text-sky-700"}`}>
                        {te.minutes} min {te.kind}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="card p-4">
              <h3 className="font-semibold text-navy mb-2">Souhrn</h3>
              {!summary ? (
                <p className="text-sm text-slateMuted">—</p>
              ) : (
                <div className="space-y-3 text-sm">
                  <p className="text-xs font-semibold uppercase text-slateMuted">Celkem {summary.total_minutes} minut</p>
                  {Object.entries(summary.by_type).map(([kind, v]) => (
                    <div key={kind} className="flex justify-between">
                      <span>{kind}</span>
                      <span className="font-semibold">{v.minutes} min ({v.count})</span>
                    </div>
                  ))}
                  <div className="pt-2 border-t border-slate-100">
                    <p className="text-xs font-semibold uppercase text-slateMuted mb-1">Podle uživatelů</p>
                    {Object.entries(summary.by_user).map(([uid, v]) => (
                      <div key={uid} className="flex justify-between text-xs">
                        <span>uživatel #{uid}</span>
                        <span>{v.minutes} min</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* FAKTURACE */}
      {active === "invoices" && (
        <div className="space-y-5">
          <div className="card p-4">
            <h3 className="font-semibold text-navy mb-3">Přidat položku</h3>
            <div className="grid sm:grid-cols-4 gap-3">
              <div>
                <label className="text-xs font-semibold text-slateMuted">Typ dokladu</label>
                <select value={invType} onChange={(e) => setInvType(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm">
                  <option value="posouzeni">posouzení (2500 Kč)</option>
                  <option value="zaloha">záloha</option>
                  <option value="final">final</option>
                  <option value="final_discount">sleva (-2500)</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slateMuted">Popis</label>
                <input value={invDesc} onChange={(e) => setInvDesc(e.target.value)} placeholder="např. Zálohová faktura" className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs font-semibold text-slateMuted">Částka Kč</label>
                <input type="number" value={invAmount} onChange={(e) => setInvAmount(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-2 text-sm" />
              </div>
              <div className="flex items-end">
                <button onClick={handleAddInvoice} disabled={busy === "inv"} className="btn-primary w-full text-sm disabled:opacity-60">
                  Přidat
                </button>
              </div>
            </div>
            <p className="text-xs text-slateMuted mt-2">
              EFEKT 2 500 Kč: položku <em>posouzení</em> vytvoří hook při „pokračujeme“, slevu −2 500 Kč hook při podpisu SoD — kontrolní součet = 0.
            </p>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold text-navy mb-2">Položky ({invoices.length})</h3>
            {invoices.length === 0 ? (
              <p className="text-sm text-slateMuted">Zatím žádné položky.</p>
            ) : (
              <div className="divide-y text-sm">
                {invoices.map((it) => (
                  <div key={String(it.id)} className="py-2 flex items-center justify-between gap-2">
                    <div>
                      <p className="font-medium text-navy">
                        {it.doc_type} {it.doc_number && <span className="text-xs bg-slate-100 rounded px-1.5 py-0.5">{it.doc_number}</span>}
                      </p>
                      <p className="text-xs text-slateMuted">{it.description || "—"} • {it.status}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`font-semibold ${(it.amount_czk ?? 0) < 0 ? "text-emerald-700" : "text-navy"}`}>
                        {Number(it.amount_czk).toLocaleString("cs-CZ")} Kč
                      </span>
                      {it.status === "draft" && isAdmin && (
                        <button onClick={() => handleIssue(it)} className="btn-navy px-3 py-1 text-xs">
                          Vystavit
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* EKONOMIKA */}
      {active === "economy" && (
        <div className="card p-4 sm:p-6">
          <h3 className="font-semibold text-navy mb-1">Ekonomika projektu</h3>
          <p className="text-xs text-slateMuted mb-4">
            Výpočet dle sazebníku (RateCard) a marže z číselníku settings (momentálně {economy ? `${(economy.margin * 100).toFixed(0)} %` : "—"}). Admin a práce se nikdy nesčítají.
          </p>
          {!economy ? (
            <p className="text-sm text-slateMuted">Není dostupná.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-slateMuted border-b">
                  <tr>
                    <th className="py-2 pr-4">Složka</th>
                    <th className="py-2 pr-4 text-right">Plán (est.)</th>
                    <th className="py-2 pr-4 text-right">Skutečnost</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  <tr>
                    <td className="py-2 pr-4">Admin minuty</td>
                    <td className="py-2 pr-4 text-right">{economy.plan.admin_minutes}</td>
                    <td className="py-2 pr-4 text-right">{economy.actual.admin_minutes}</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4">Admin náklad (Kč)</td>
                    <td className="py-2 pr-4 text-right">{economy.plan.admin_cost.toLocaleString("cs-CZ")} Kč</td>
                    <td className="py-2 pr-4 text-right">{economy.actual.admin_cost.toLocaleString("cs-CZ")} Kč</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4">Práce minuty</td>
                    <td className="py-2 pr-4 text-right">{economy.plan.work_minutes}</td>
                    <td className="py-2 pr-4 text-right">{economy.actual.work_minutes}</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4">Práce náklad (Kč)</td>
                    <td className="py-2 pr-4 text-right">{economy.plan.work_cost.toLocaleString("cs-CZ")} Kč</td>
                    <td className="py-2 pr-4 text-right">{economy.actual.work_cost.toLocaleString("cs-CZ")} Kč</td>
                  </tr>
                  <tr className="font-bold">
                    <td className="py-2 pr-4">Náklad celkem</td>
                    <td className="py-2 pr-4 text-right">{economy.plan.total_cost.toLocaleString("cs-CZ")} Kč</td>
                    <td className="py-2 pr-4 text-right">{economy.actual.total_cost.toLocaleString("cs-CZ")} Kč</td>
                  </tr>
                </tbody>
              </table>
              <div className="mt-4 grid sm:grid-cols-2 gap-3">
                <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                  <p className="text-xs text-slateMuted">Doporučená cena (plán × {((economy.margin + 1) * 100).toFixed(0)} %)</p>
                  <p className="text-lg font-bold text-navy">{economy.sell.toLocaleString("cs-CZ")} Kč</p>
                </div>
                <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                  <p className="text-xs text-slateMuted">Podle skutečnosti</p>
                  <p className="text-lg font-bold text-antelonGreen">{economy.sell_actual.toLocaleString("cs-CZ")} Kč</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* HISTORIE */}
      {active === "events" && (
        <div className="card p-4">
          <h3 className="font-semibold text-navy mb-2">Historie kroků ({view.events.length})</h3>
          {view.events.length === 0 ? (
            <p className="text-sm text-slateMuted">Žádné události.</p>
          ) : (
            <div className="divide-y text-sm max-h-[480px] overflow-auto">
              {view.events.map((ev) => (
                <div key={String(ev.id)} className="py-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100">{ev.action}</span>
                    <span className="font-medium text-navy">{ev.step}</span>
                    <span className="text-xs text-slateMuted">
                      {ev.from_status} → {ev.to_status}
                    </span>
                  </div>
                  <p className="text-xs text-slateMuted mt-0.5">
                    {ev.at ? new Date(ev.at).toLocaleString("cs-CZ") : ""} • uživatel #{ev.user_id}
                    {ev.note ? ` • ${ev.note}` : ""}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}