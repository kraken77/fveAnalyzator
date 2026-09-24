import { useAuth } from "../context/AuthContext";

/** Přepínač rolí — viditelný jen pokud má uživatel víc rolí. */
export default function RoleSwitcher() {
  const { roles, activeRole, setActiveRole } = useAuth();

  if (roles.length <= 1) {
    return (
      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-antelonGreen text-navy">
        {activeRole}
      </span>
    );
  }

  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span className="opacity-70 hidden sm:inline">Role:</span>
      <select
        value={activeRole}
        onChange={(e) => setActiveRole(e.target.value)}
        className="bg-white/10 border border-white/20 text-white text-xs font-semibold rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-antelonGreen"
        data-testid="role-switcher"
      >
        {roles.map((r) => (
          <option key={r} value={r} className="text-navy">
            {r}
          </option>
        ))}
      </select>
    </label>
  );
}
