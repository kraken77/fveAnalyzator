import { useEffect, useState } from "react";
import client from "../api/client";

interface User {
  id: string | number;
  email: string;
  role: string;
  created_at?: string;
}

interface Appliance {
  id?: string | number;
  name: string;
  is_active?: boolean;
  power_w?: number;
  label?: string;
}

type Tab = "users" | "appliances" | "ote";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("users");

  // users
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState<string | null>(null);

  // appliances
  const [appliances, setAppliances] = useState<Appliance[]>([]);
  const [applLoading, setApplLoading] = useState(false);
  const [applError, setApplError] = useState<string | null>(null);

  // ote
  const [oteStatus, setOteStatus] = useState<Record<string, unknown> | null>(null);
  const [oteLoading, setOteLoading] = useState(false);
  const [oteMsg, setOteMsg] = useState<string | null>(null);

  const fetchUsers = async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      // try multiple possible endpoints
      let res;
      try {
        res = await client.get("/admin/users");
      } catch {
        res = await client.get("/auth/users");
      }
      const data = res.data as unknown;
      const list: User[] = Array.isArray(data)
        ? (data as User[])
        : ((data as { users?: User[] })?.users ?? []);
      setUsers(list);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Načtení uživatelů selhalo";
      setUsersError(m);
    } finally {
      setUsersLoading(false);
    }
  };

  const fetchAppliances = async () => {
    setApplLoading(true);
    setApplError(null);
    try {
      const res = await client.get("/admin/appliances");
      const data = res.data as unknown;
      const list: Appliance[] = Array.isArray(data)
        ? (data as Appliance[])
        : ((data as { appliances?: Appliance[] })?.appliances ?? []);
      // normalize if object map
      if (!Array.isArray(data) && typeof data === "object" && data !== null) {
        const obj = data as Record<string, unknown>;
        if (!obj.appliances && !Array.isArray(obj)) {
          // maybe { "boiler": {is_active: true, ...}, ...}
          const entries = Object.entries(obj);
          if (entries.length > 0 && typeof entries[0][1] === "object") {
            const mapped: Appliance[] = entries.map(([name, val]) => ({
              name,
              ...(val as Record<string, unknown>),
            })) as Appliance[];
            setAppliances(mapped);
            setApplLoading(false);
            return;
          }
        }
      }
      setAppliances(list);
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Načtení spotřebičů selhalo";
      setApplError(m);
    } finally {
      setApplLoading(false);
    }
  };

  const fetchOte = async () => {
    setOteLoading(true);
    try {
      const res = await client.get("/ote/status");
      setOteStatus(res.data as Record<string, unknown>);
    } catch {
      // fallback to admin ote
      try {
        const res2 = await client.get("/admin/ote/status");
        setOteStatus(res2.data as Record<string, unknown>);
      } catch {
        setOteStatus({ status: "unknown", note: "OTE status nedostupný" });
      }
    } finally {
      setOteLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "users") fetchUsers();
    if (tab === "appliances") fetchAppliances();
    if (tab === "ote") fetchOte();
  }, [tab]);

  useEffect(() => {
    // preload all
    fetchUsers();
    fetchAppliances();
    fetchOte();
  }, []);

  const handleChangeRole = async (userId: string | number, newRole: string) => {
    try {
      await client.put(`/admin/users/${userId}/role`, { role: newRole }).catch(async () => {
        await client.put(`/admin/users/${userId}`, { role: newRole });
      });
      await fetchUsers();
    } catch {
      alert("Změna role selhala");
    }
  };

  const handleToggleAppliance = async (appl: Appliance) => {
    try {
      await client.put(`/admin/appliances/${encodeURIComponent(appl.name)}`, {
        is_active: !appl.is_active,
      });
      await fetchAppliances();
    } catch {
      alert("Změna stavu spotřebiče selhala");
    }
  };

  const handleOteUpdate = async () => {
    setOteMsg(null);
    try {
      await client.post("/ote/update");
      setOteMsg("OTE data aktualizována");
      await fetchOte();
    } catch (e: unknown) {
      const m =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Aktualizace OTE selhala";
      setOteMsg(m);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy">Administrace</h1>
        <p className="text-sm text-slateMuted mt-1">Správa uživatelů, spotřebičů a OTE (pouze role admin)</p>
      </div>

      <div className="flex gap-2 border-b">
        {(
          [
            { id: "users", label: "Uživatelé" },
            { id: "appliances", label: "Spotřebiče" },
            { id: "ote", label: "OTE" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition ${
              tab === t.id
                ? "border-antelonGreen text-navy"
                : "border-transparent text-slateMuted hover:text-navy"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-navy">Uživatelé ({users.length})</h3>
            <button onClick={fetchUsers} className="btn-secondary text-xs">
              Obnovit
            </button>
          </div>
          {usersLoading ? (
            <p className="text-sm text-slateMuted">Načítám...</p>
          ) : usersError ? (
            <p className="text-sm text-red-600">{usersError}</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-slateMuted">Žádní uživatelé.</p>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slateMuted border-b">
                    <th className="py-2 px-2">E-mail</th>
                    <th className="py-2 px-2">Role</th>
                    <th className="py-2 px-2">Akce</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={String(u.id)} className="border-b last:border-0">
                      <td className="py-2 px-2 font-medium text-navy">{u.email}</td>
                      <td className="py-2 px-2">
                        <span className="text-xs font-semibold bg-navy text-white px-2 py-1 rounded">
                          {u.role}
                        </span>
                      </td>
                      <td className="py-2 px-2">
                        <select
                          value={u.role}
                          onChange={(e) => handleChangeRole(u.id, e.target.value)}
                          className="border border-slate-200 rounded px-2 py-1 text-xs"
                        >
                          <option value="customer">customer</option>
                          <option value="antelon">antelon</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "appliances" && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-navy">Spotřebiče ({appliances.length})</h3>
            <button onClick={fetchAppliances} className="btn-secondary text-xs">
              Obnovit
            </button>
          </div>
          {applLoading ? (
            <p className="text-sm text-slateMuted">Načítám...</p>
          ) : applError ? (
            <p className="text-sm text-red-600">{applError}</p>
          ) : appliances.length === 0 ? (
            <p className="text-sm text-slateMuted">Žádné spotřebiče.</p>
          ) : (
            <div className="divide-y">
              {appliances.map((a) => (
                <div key={a.name} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-medium text-navy">{a.label || a.name}</p>
                    <p className="text-xs text-slateMuted">
                      {a.power_w ? `${a.power_w} W` : ""} {a.is_active !== undefined ? `• ${a.is_active ? "aktivní" : "neaktivní"}` : ""}
                    </p>
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!a.is_active}
                      onChange={() => handleToggleAppliance(a)}
                      className="accent-antelonGreen"
                    />
                    <span className="text-xs text-slateMuted">{a.is_active ? "Zapnuto" : "Vypnuto"}</span>
                  </label>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "ote" && (
        <div className="space-y-4">
          <div className="card p-5 border-l-4 border-l-antelonGreen">
            <h3 className="font-semibold text-navy">OTE status</h3>
            {oteLoading ? (
              <p className="text-sm text-slateMuted mt-2">Načítám...</p>
            ) : oteStatus ? (
              <pre className="mt-3 bg-slate-50 border rounded p-3 text-xs overflow-auto">
                {JSON.stringify(oteStatus, null, 2)}
              </pre>
            ) : (
              <p className="text-sm text-slateMuted mt-2">Žádná data.</p>
            )}
            <button onClick={handleOteUpdate} className="btn-navy mt-3 text-sm">
              Aktualizovat OTE data
            </button>
            {oteMsg && <p className="text-sm mt-2 bg-emerald-50 border border-emerald-200 text-emerald-700 px-3 py-2 rounded">{oteMsg}</p>}
            <p className="text-xs text-slateMuted mt-2">Pouze antelon/admin může provést update.</p>
          </div>
        </div>
      )}
    </div>
  );
}
