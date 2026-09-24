import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import client from "../api/client";

export interface User {
  id: number | string;
  email: string;
  role: string;
  roles?: string[];
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
  /** primární role + roles pole */
  roles: string[];
  /** aktuálně aktivní role (role-switcher) */
  activeRole: string;
  setActiveRole: (role: string) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function normalizeRoles(data: Record<string, unknown>, fallbackPrimary?: string): string[] {
  const arr = data.roles;
  if (Array.isArray(arr) && arr.length > 0) {
    return arr.map(String);
  }
  const primary = (data.role as string | undefined) || fallbackPrimary;
  return primary ? [primary] : [];
}

function parseTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return json && typeof json === "object" ? (json as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function readStoredUser(): User | null {
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(readStoredUser);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);
  const [activeRole, setActiveRoleState] = useState<string>(() => {
    const stored = localStorage.getItem("activeRole");
    const u = readStoredUser();
    if (stored && u && (u.roles ?? [u.role]).includes(stored)) return stored;
    return u?.role || "customer";
  });

  const applyUser = useCallback((u: User) => {
    setUser(u);
    localStorage.setItem("user", JSON.stringify(u));
    const roles = u.roles && u.roles.length ? u.roles : [u.role];
    setActiveRoleState((prev) => (prev && roles.includes(prev) ? prev : u.role));
  }, []);

  const setActiveRole = useCallback((role: string) => {
    localStorage.setItem("activeRole", role);
    setActiveRoleState(role);
  }, []);

  const fetchMe = useCallback(
    async (tok: string | null) => {
      if (!tok) {
        setLoading(false);
        return;
      }
      try {
        const res = await client.get("/auth/me", {
          headers: { Authorization: `Bearer ${tok}` },
        });
        const data = res.data as Record<string, unknown>;
        const u: User = {
          id: (data.id as string | number) ?? 0,
          email: (data.email as string) ?? "",
          role: (data.role as string) ?? "customer",
          roles: normalizeRoles(data),
        };
        applyUser(u);
      } catch {
        const payload = parseTokenPayload(tok);
        const fallback = readStoredUser();
        if (payload && (payload.email || payload.sub)) {
          const primary = (payload.role as string) || fallback?.role || "customer";
          applyUser({
            id: (payload.id as string | number) ?? fallback?.id ?? 0,
            email: (payload.email as string) ?? (payload.sub as string) ?? "",
            role: primary,
            roles: fallback?.roles ?? [primary],
          });
        }
      } finally {
        setLoading(false);
      }
    },
    [applyUser],
  );

  useEffect(() => {
    fetchMe(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await client.post("/auth/login", { email, password });
      const data = res.data as Record<string, unknown>;
      const tok =
        (data.access_token as string) ||
        (data.token as string) ||
        (data.accessToken as string) ||
        (data.jwt as string) ||
        "";
      if (!tok) throw new Error("Token not returned from server");
      localStorage.setItem("token", tok);
      setToken(tok);
      setLoading(true);
      try {
        const meRes = await client.get("/auth/me", {
          headers: { Authorization: `Bearer ${tok}` },
        });
        const md = meRes.data as Record<string, unknown>;
        applyUser({
          id: (md.id as string | number) ?? 0,
          email: (md.email as string) ?? email,
          role: (md.role as string) ?? "customer",
          roles: normalizeRoles(md),
        });
      } catch {
        const payload = parseTokenPayload(tok);
        const primary = (payload?.role as string) ?? "customer";
        applyUser({ id: (payload?.id as string | number) ?? 0, email, role: primary, roles: [primary] });
      } finally {
        setLoading(false);
      }
    },
    [applyUser],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await client.post("/auth/register", { email, password });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    localStorage.removeItem("activeRole");
    setToken(null);
    setUser(null);
  }, []);

  const refreshMe = useCallback(async () => {
    const t = localStorage.getItem("token");
    setLoading(true);
    await fetchMe(t);
  }, [fetchMe]);

  const roles = useMemo(() => (user?.roles && user.roles.length ? user.roles : user ? [user.role] : []), [user]);
  const effectiveActiveRole = useMemo(() => (activeRole && roles.includes(activeRole) ? activeRole : user?.role || "customer"), [activeRole, roles, user]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, loading, login, register, logout, refreshMe, roles, activeRole: effectiveActiveRole, setActiveRole }),
    [user, token, loading, login, register, logout, refreshMe, roles, effectiveActiveRole, setActiveRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function hasAnyRole(user: { role: string; roles?: string[] } | null, wanted: string[]): boolean {
  if (!user) return false;
  const all = user.roles && user.roles.length ? user.roles : [user.role];
  return all.some((r) => wanted.includes(r));
}