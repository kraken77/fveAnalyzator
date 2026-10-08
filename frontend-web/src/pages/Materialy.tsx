import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { hasAnyRole, useAuth } from "../context/AuthContext";
import {
  addMaterial,
  addProjectMaterial,
  getMaterials,
  getMaterialsBalance,
  listProjects,
  setMaterialPrice,
} from "../api/pipeline";
import type { Material, MaterialBalanceRow, ProjectLite } from "../types";

const LANES = [
  { key: "plan_qty", label: "Plán" },
  { key: "order_qty", label: "Objednávka" },
  { key: "issue_qty", label: "Výdej" },
  { key: "actual_qty", label: "Skutečnost" },
] as const;

const LANE_POST: Record<string, string> = {
  plan_qty: "plan",
  order_qty: "order",
  issue_qty: "issue",
  actual_qty: "actual",
};

export default function Materialy() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const canManage = hasAnyRole(user, ["admin", "antelon"]);

  const pid = id ?? "";
  const [projects, setProjects] = useState<ProjectLite[]>([]);
  const [selProject, setSelProject] = useState<string>(pid);

  const [materials, setMaterials] = useState<Material[]>([]);
  const [balance, setBalance] = useState<MaterialBalanceRow[]>([]);

  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // form: new material
  const [mCode, setMCode] = useState("");
  const [mName, setMName] = useState("");
  const [mUnit, setMUnit] = useState("ks");
  const [mPrice, setMPrice] = useState("0");

  // form: nová cena s platností
  const [priceMatId, setPriceMatId] = useState("");
  const [newPrice, setNewPrice] = useState("0");
  const [validFrom, setValidFrom] = useState(() => new Date().toISOString().slice(0, 10));

  // form: add to project
  const [addMatId, setAddMatId] = useState("");
  const [addQty, setAddQty] = useState("1");
  const [addLane, setAddLane] = useState("plan_qty");

  const loadCatalog = useCallback(async () => {
    try {
      setMaterials(await getMaterials());
    } catch {
      setMaterials([]);
    }
  }, []);

  const loadProjectData = useCallback(
    async (projectId: string) => {
      if (!projectId) return;
      try {
        setBalance(await getMaterialsBalance(projectId));
      } catch {
        setBalance([]);
      }
    },
    [],
  );

  useEffect(() => {
    loadCatalog();
    if (!pid) {
      listProjects()
        .then((l) => setProjects(l))
        .catch(() => setProjects([]));
    }
  }, [loadCatalog, pid]);

  useEffect(() => {
    const target = pid || selProject;
    if (target) {
      loadProjectData(target);
    }
  }, [pid, selProject, loadProjectData]);

  const activePid = pid || selProject;

  const handleAddMaterial = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const m = await addMaterial({ code: mCode, name: mName, unit: mUnit, price: Number(mPrice) || 0 });
      setMsg(`Materiál ${m.code} přidán`);
      setMCode("");
      setMName("");
      setMPrice("0");
      setAddMatId(String(m.id));
      await loadCatalog();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Přidání materiálu selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSetPrice = async () => {
    if (!priceMatId) {
      setMsg("Vyberte materiál pro změnu ceny.");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await setMaterialPrice(priceMatId, {
        price: Number(newPrice) || 0,
        valid_from: validFrom,
      });
      setMsg(`Nová cena materiálu od ${r.valid_from}: ${Number(r.price).toLocaleString("cs-CZ")} Kč`);
      setAddMatId(priceMatId);
      await loadCatalog();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Změna ceny selhala";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(false);
    }
  };

  const handleAddToProject = async () => {
    if (!activePid || !addMatId) {
      setMsg("Vyberte materiál a projekt.");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const pm = await addProjectMaterial(activePid, {
        material_id: Number(addMatId),
        qty: Number(addQty) || 0,
        lane: LANE_POST[addLane] ?? "plan",
      });
      setMsg(`Přidáno (lane ${pm.lane}) — cena ze snapshotu ${pm.price_snapshot} Kč`);
      await loadProjectData(activePid);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Přiřazení selhalo";
      setMsg(`Chyba: ${m}`);
    } finally {
      setBusy(false);
    }
  };

  const totalPlan = useMemo(
    () => balance.reduce((acc, r) => acc + (r.total_plan_czk ?? 0), 0),
    [balance],
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-navy">
            {pid ? "Materiály projektu" : "Materiály — sklad"}
          </h1>
          <p className="text-sm text-slateMuted">
            Bilance plán / objednávka / výdej / skutečnost
          </p>
        </div>
        {pid && (
          <Link to={`/projects/${pid}/pipeline`} className="btn-secondary text-sm">
            ← Zpět na pipeline
          </Link>
        )}
      </div>

      {msg && (
        <div className={`px-3 py-2 rounded text-sm flex justify-between ${msg.startsWith("Chyba") ? "bg-red-50 border border-red-200 text-red-700" : "bg-emerald-50 border border-emerald-200 text-emerald-800"}`}>
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="font-bold ml-4">×</button>
        </div>
      )}

      {!pid && (
        <div className="card p-4 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
          <label className="text-sm font-semibold text-navy">Projekt:</label>
          <select
            value={selProject}
            onChange={(e) => setSelProject(e.target.value)}
            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">— vyberte projekt —</option>
            {projects.map((p) => (
              <option key={String(p.id)} value={String(p.id)}>
                #{String(p.id)} {p.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-5">
        {/* číselník */}
        <div className="card p-4 lg:col-span-1">
          <h3 className="font-semibold text-navy mb-2">Číselník materiálů ({materials.length})</h3>
          <div className="max-h-72 overflow-auto divide-y text-sm">
            {materials.map((m) => (
              <div key={String(m.id)} className="py-1.5 flex justify-between gap-2">
                <span className="font-mono text-xs text-slateMuted">{m.code}</span>
                <span className="flex-1">{m.name} <span className="text-xs text-slate-400">({m.unit})</span></span>
                <span className="font-semibold whitespace-nowrap">{Number(m.price).toLocaleString("cs-CZ")} Kč</span>
              </div>
            ))}
            {materials.length === 0 && <p className="text-sm text-slateMuted py-2">Prázdný číselník.</p>}
          </div>

          {canManage && (
            <>
            <div className="mt-3 pt-3 border-t border-slate-100 space-y-2">
              <p className="text-xs font-semibold uppercase text-slateMuted">Nový materiál</p>
              <div className="grid grid-cols-2 gap-2">
                <input value={mCode} onChange={(e) => setMCode(e.target.value)} placeholder="kód" className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                <input value={mName} onChange={(e) => setMName(e.target.value)} placeholder="název" className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                <input value={mUnit} onChange={(e) => setMUnit(e.target.value)} placeholder="jednotka" className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                <input type="number" value={mPrice} onChange={(e) => setMPrice(e.target.value)} placeholder="cena Kč" className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
              </div>
              <button onClick={handleAddMaterial} disabled={busy || !mCode || !mName} className="btn-navy w-full text-sm disabled:opacity-50">
                Přidat do číselníku
              </button>
            </div>
            <div className="pt-3 border-t border-slate-100 space-y-2">
              <p className="text-xs font-semibold uppercase text-slateMuted">Nová cena s platností</p>
              <select
                value={priceMatId}
                onChange={(e) => {
                  setPriceMatId(e.target.value);
                  const m = materials.find((x) => String(x.id) === e.target.value);
                  setNewPrice(String(m?.price ?? 0));
                }}
                className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
              >
                <option value="">— materiál —</option>
                {materials.map((m) => (
                  <option key={String(m.id)} value={String(m.id)}>
                    {m.code} — {m.name}
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-2 gap-2">
                <input type="number" min={0} value={newPrice}
                       onChange={(e) => setNewPrice(e.target.value)}
                       placeholder="cena Kč"
                       className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                <input type="date" value={validFrom}
                       onChange={(e) => setValidFrom(e.target.value)}
                       className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
              </div>
              <button onClick={handleSetPrice} disabled={busy || !priceMatId}
                      className="btn-navy w-full text-sm disabled:opacity-50">
                Uložit cenu
              </button>
            </div>
            </>
          )}
        </div>

        {/* matice projektu */}
        <div className="card p-4 lg:col-span-2">
          <h3 className="font-semibold text-navy mb-2">
            {activePid ? `Bilance projektu #${activePid}` : "Vyberte projekt"}
          </h3>
          {!activePid ? (
            <p className="text-sm text-slateMuted">Nejdřív vyberte projekt vlevo nahoře.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slateMuted border-b">
                    <tr>
                      <th className="py-2 pr-3">Materiál</th>
                      {LANES.map((l) => (
                        <th key={l.key} className="py-2 pr-3 text-right">{l.label}</th>
                      ))}
                      <th className="py-2 pr-3 text-right">Cena / ks</th>
                      <th className="py-2 text-right">Plán Kč</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {balance.map((r) => (
                      <tr key={String(r.material_id)}>
                        <td className="py-2 pr-3">
                          <span className="font-mono text-xs text-slate-400">{r.code}</span>{" "}
                          <span className="font-medium">{r.name}</span>
                        </td>
                        {LANES.map((l) => (
                          <td key={l.key} className="py-2 pr-3 text-right">{r[l.key] ?? 0}</td>
                        ))}
                        <td className="py-2 pr-3 text-right">{Number(r.price).toLocaleString("cs-CZ")}</td>
                        <td className="py-2 text-right font-semibold">{Number(r.total_plan_czk ?? 0).toLocaleString("cs-CZ")}</td>
                      </tr>
                    ))}
                    {balance.length === 0 && (
                      <tr><td colSpan={7} className="py-6 text-center text-slate-400">Žádné materiály přiřazené.</td></tr>
                    )}
                  </tbody>
                  {balance.length > 0 && (
                    <tfoot>
                      <tr className="border-t font-bold">
                        <td className="py-2 pr-3">Celkem</td>
                        <td colSpan={6} />
                        <td className="py-2 text-right">{totalPlan.toLocaleString("cs-CZ")} Kč</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>

              {canManage && (
                <div className="mt-4 pt-3 border-t border-slate-100">
                  <p className="text-xs font-semibold uppercase text-slateMuted mb-2">Přiřadit materiál</p>
                  <div className="grid sm:grid-cols-4 gap-2">
                    <select value={addMatId} onChange={(e) => setAddMatId(e.target.value)} className="border border-slate-200 rounded-lg px-2 py-2 text-sm">
                      <option value="">— materiál —</option>
                      {materials.map((m) => (
                        <option key={String(m.id)} value={String(m.id)}>
                          {m.code} — {m.name}
                        </option>
                      ))}
                    </select>
                    <input type="number" min={0} value={addQty} onChange={(e) => setAddQty(e.target.value)} placeholder="množství" className="border border-slate-200 rounded-lg px-2 py-2 text-sm" />
                    <select value={addLane} onChange={(e) => setAddLane(e.target.value)} className="border border-slate-200 rounded-lg px-2 py-2 text-sm">
                      {LANES.map((l) => (
                        <option key={l.key} value={l.key}>{l.label}</option>
                      ))}
                    </select>
                    <button onClick={handleAddToProject} disabled={busy || !addMatId} className="btn-primary text-sm disabled:opacity-50">
                      Přidat
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}