import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import {
  adminSetUserRoles,
  getTemplates,
  getTemplateSteps,
  importDispecink,
  updateTemplateStep,
} from "../api/pipeline";
import type { PipelineTemplate, TemplateStep } from "../types";

const ROLE_CISELNIK = [
  "admin",
  "antelon",
  "sales",
  "designer",
  "buyer",
  "warehouse",
  "subsidy",
  "connection",
  "electrician",
  "roofer",
  "inspector",
  "customer",
];

interface RateCardRow {
  id: number | string;
  role: string;
  kind: string;
  rate_czk_h: number;
  active: boolean;
}

type AdminTab = "import" | "templates" | "users" | "rates";

export default function AdminPipeline() {
  const [active, setActive] = useState<AdminTab>("import");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-navy">Administrace — procesní pipeline</h1>
        <p className="text-sm text-slateMuted">Import dispečinku, šablony, uživatelé a sazby.</p>
      </div>

      <div className="border-b border-slate-200 overflow-x-auto">
        <div className="flex gap-1 sm:gap-2">
          {([
            ["import", "Import"],
            ["templates", "Šablony"],
            ["users", "Uživatelé a role"],
            ["rates", "Sazby (RateCard)"],
          ] as [AdminTab, string][]).map(([tid, label]) => (
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

      {active === "import" && <ImportTab />}
      {active === "templates" && <TemplatesTab />}
      {active === "users" && <UsersTab />}
      {active === "rates" && <RatesTab />}

      <div className="text-xs text-slateMuted">
        <Link to="/dispecink" className="hover:text-navy">← Zpět na dispečink</Link>
      </div>
    </div>
  );
}

function ImportTab() {
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await importDispecink(file);
      setMsg(`Import OK — ${res.imported ?? "?"} projektů${res.skipped ? `, přeskočeno ${res.skipped}` : ""}`);
      setOk(true);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Import selhal";
      setMsg(`Chyba: ${m}`);
      setOk(false);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="card p-5">
      <h3 className="font-semibold text-navy">Import procesního dispečinku (XLSX)</h3>
      <p className="text-sm text-slateMuted mt-1">
        Načte <code className="bg-slate-100 px-1 rounded">PROCESNÍ DISPEČINK.xlsx</code> (idempotentní — duplicity se přeskočí).
      </p>
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      <button onClick={() => fileRef.current?.click()} disabled={busy} className="btn-navy mt-4 text-sm disabled:opacity-60">
        {busy ? "Importuji..." : "Vybrat soubor a importovat"}
      </button>
      {msg && (
        <p className={`mt-3 text-sm ${ok ? "text-emerald-700" : "text-red-700"}`}>{msg}</p>
      )}
    </div>
  );
}

function TemplatesTab() {
  const [templates, setTemplates] = useState<PipelineTemplate[]>([]);
  const [selId, setSelId] = useState<string>("");
  const [steps, setSteps] = useState<TemplateStep[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const loadTemplates = useCallback(async () => {
    const tpls = await getTemplates();
    setTemplates(tpls);
    if (tpls.length && !selId) setSelId(String(tpls[0].id));
  }, [selId]);

  useEffect(() => {
    loadTemplates().catch(() => setTemplates([]));
  }, [loadTemplates]);

  useEffect(() => {
    if (!selId) return;
    getTemplateSteps(selId)
      .then(setSteps)
      .catch(() => setSteps([]));
  }, [selId]);

  const handleSave = async (step: TemplateStep, field: "name" | "est_admin_minutes" | "est_work_minutes", value: string | number) => {
    setBusy(`${step.id}:${field}`);
    setMsg(null);
    try {
      await updateTemplateStep(selId, step.id, { [field]: field === "name" ? String(value) : Number(value) });
      setMsg(`Uloženo: ${step.code} — ${field} = ${value}`);
      const fresh = await getTemplateSteps(selId);
      setSteps(fresh);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Uložení selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      {msg && (
        <div className="px-3 py-2 rounded text-sm bg-emerald-50 border border-emerald-200 text-emerald-800 flex justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold">×</button>
        </div>
      )}
      <div className="card p-4">
        <h3 className="font-semibold text-navy mb-2">Šablony ({templates.length})</h3>
        <div className="flex flex-wrap gap-2">
          {templates.map((t) => (
            <button
              key={String(t.id)}
              onClick={() => setSelId(String(t.id))}
              className={`px-3 py-1.5 text-sm rounded-lg border transition ${
                selId === String(t.id) ? "bg-navy text-white border-navy" : "bg-white border-slate-200 text-navy hover:bg-slate-50"
              }`}
            >
              {t.name}
            </button>
          ))}
        </div>
      </div>

      <div className="card p-4">
        <h3 className="font-semibold text-navy mb-2">Kroky šablony ({steps.length})</h3>
        <div className="overflow-x-auto max-h-[520px]">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slateMuted border-b sticky top-0 bg-white">
              <tr>
                <th className="py-2 pr-3">#</th>
                <th className="py-2 pr-3">Kód</th>
                <th className="py-2 pr-3">Název (editable)</th>
                <th className="py-2 pr-3">Fáze</th>
                <th className="py-2 pr-3 text-right">Admin min</th>
                <th className="py-2 pr-3 text-right">Práce min</th>
                <th className="py-2">Model</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {steps.map((s) => (
                <tr key={String(s.id)}>
                  <td className="py-1.5 pr-3 text-slate-400">{s.order}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-slateMuted">{s.code}</td>
                  <td className="py-1.5 pr-3">
                    <input
                      defaultValue={s.name}
                      key={`name:${s.id}`}
                      onBlur={(e) => {
                        if (e.target.value !== s.name) handleSave(s, "name", e.target.value);
                      }}
                      className="w-full border border-transparent hover:border-slate-200 focus:border-antelonGreen rounded px-2 py-1 text-sm focus:outline-none"
                    />
                  </td>
                  <td className="py-1.5 pr-3 text-xs">{s.phase}</td>
                  <td className="py-1.5 pr-3">
                    <input
                      type="number"
                      key={`admin:${s.id}`}
                      defaultValue={s.est_admin_minutes ?? 0}
                      onBlur={(e) => {
                        const v = Number(e.target.value) || 0;
                        if (v !== (s.est_admin_minutes ?? 0)) handleSave(s, "est_admin_minutes", v);
                      }}
                      className="w-20 border border-transparent hover:border-slate-200 focus:border-antelonGreen rounded px-2 py-1 text-sm text-right focus:outline-none"
                    />
                  </td>
                  <td className="py-1.5 pr-3">
                    <input
                      type="number"
                      key={`work:${s.id}`}
                      defaultValue={s.est_work_minutes ?? 0}
                      onBlur={(e) => {
                        const v = Number(e.target.value) || 0;
                        if (v !== (s.est_work_minutes ?? 0)) handleSave(s, "est_work_minutes", v);
                      }}
                      className="w-20 border border-transparent hover:border-slate-200 focus:border-antelonGreen rounded px-2 py-1 text-sm text-right focus:outline-none"
                    />
                  </td>
                  <td className="py-1.5 text-xs">
                    {s.state_model} {busy === `${s.id}:` ? "…" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slateMuted mt-2">
          Úpravy se ukládají po opuštění pole (onBlur). Změny ovlivní jen nově připojované projekty.
        </p>
      </div>
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<Array<{ id: number | string; email: string; role: string; roles?: string[] }>>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await client.get("/admin/users");
    setUsers(res.data as Array<{ id: number | string; email: string; role: string; roles?: string[] }>);
  }, []);

  useEffect(() => {
    load().catch(() => setUsers([]));
  }, [load]);

  const toggleRole = async (u: { id: number | string; roles?: string[]; role: string }, role: string) => {
    const current = u.roles && u.roles.length ? u.roles : [u.role];
    const next = current.includes(role) ? current.filter((r) => r !== role) : [...current, role];
    if (!next.length) {
      setMsg("Uživatel musí mít alespoň jednu roli.");
      return;
    }
    try {
      await adminSetUserRoles(u.id, next);
      setMsg(`Role uživatele uloženy: ${next.join(", ")}`);
      await load();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Uložení rolí selhalo";
      setMsg(`Chyba: ${m}`);
    }
  };

  return (
    <div className="card p-4">
      {msg && (
        <div className="px-3 py-2 mb-3 rounded text-sm bg-emerald-50 border border-emerald-200 text-emerald-800 flex justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold">×</button>
        </div>
      )}
      <h3 className="font-semibold text-navy mb-2">Uživatelé a role ({users.length})</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slateMuted border-b">
            <tr>
              <th className="py-2 pr-3">E-mail</th>
              <th className="py-2 pr-3">Primární role</th>
              <th className="py-2">Role (multi)</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.map((u) => {
              const current = u.roles && u.roles.length ? u.roles : [u.role];
              return (
                <tr key={String(u.id)}>
                  <td className="py-2 pr-3">{u.email}</td>
                  <td className="py-2 pr-3">
                    <span className="text-xs bg-slate-100 border border-slate-200 rounded px-2 py-0.5">{u.role}</span>
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-1.5">
                      {ROLE_CISELNIK.map((r) => {
                        const on = current.includes(r);
                        return (
                          <button
                            key={r}
                            onClick={() => toggleRole(u, r)}
                            className={`text-xs px-2 py-0.5 rounded border transition ${
                              on
                                ? "bg-navy text-white border-navy"
                                : "bg-white text-slateMuted border-slate-200 hover:border-navy hover:text-navy"
                            }`}
                          >
                            {r}
                          </button>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RatesTab() {
  const [rows, setRows] = useState<RateCardRow[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await client.get("/admin/rate-cards");
    setRows(res.data as RateCardRow[]);
  }, []);

  useEffect(() => {
    load().catch(() => setRows([]));
  }, [load]);

  const save = async (id: number | string, field: "rate_czk_h" | "active", value: number | boolean) => {
    setBusy(`${id}:${field}`);
    try {
      await client.put(`/admin/rate-cards/${id}`, { [field]: value });
      setMsg("Sazba uložena");
      await load();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Uložení selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card p-4">
      {msg && (
        <div className="px-3 py-2 mb-3 rounded text-sm bg-emerald-50 border border-emerald-200 text-emerald-800 flex justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold">×</button>
        </div>
      )}
      <h3 className="font-semibold text-navy mb-2">Sazby (Kč/hod)</h3>
      <p className="text-xs text-slateMuted mb-3">
        Používají se pro výpočet ekonomiky (admin vs work se nikdy nesčítají). Uloží se po opuštění pole.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slateMuted border-b">
            <tr>
              <th className="py-2 pr-3">Role</th>
              <th className="py-2 pr-3">Kind</th>
              <th className="py-2 pr-3 text-right">Kč/h</th>
              <th className="py-2">Aktivní</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => (
              <tr key={String(r.id)}>
                <td className="py-1.5 pr-3">{r.role}</td>
                <td className="py-1.5 pr-3 text-xs text-slateMuted">{r.kind}</td>
                <td className="py-1.5 pr-3">
                  <input
                    type="number"
                    key={`rate:${r.id}`}
                    defaultValue={r.rate_czk_h}
                    onBlur={(e) => {
                      const v = Number(e.target.value) || 0;
                      if (v !== r.rate_czk_h) save(r.id, "rate_czk_h", v);
                    }}
                    className="w-24 border border-transparent hover:border-slate-200 focus:border-antelonGreen rounded px-2 py-1 text-sm text-right focus:outline-none"
                  />
                </td>
                <td className="py-1.5">
                  <input
                    type="checkbox"
                    defaultChecked={r.active}
                    disabled={busy === `${r.id}:active`}
                    onChange={(e) => save(r.id, "active", e.target.checked)}
                    className="w-4 h-4 accent-antelonGreen"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}