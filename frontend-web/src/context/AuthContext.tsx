import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import client from "../api/client";

export type UserRole = "admin" | "antelon" | "customer";

export interface User {
  id: number | string;
  email: string;
  role: UserRole;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function parseTokenPayload(token: string): Partial<User> | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    // try common fields
    return {
      email: json.email || json.sub || json.username,
      role: json.role || json.user_role,
      id: json.id || json.user_id || json.sub,
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem("user");
    if (raw) {
      try {
        return JSON.parse(raw) as User;
      } catch {
        return null;
      }
    }
    return null;
  });
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async (tok: string | null) => {
    if (!tok) {
      setLoading(false);
      return;
    }
    try {
      const res = await client.get("/auth/me", {
        headers: { Authorization: `Bearer ${tok}` },
      });
      const data = res.data as Record<string, unknown>;
      // normalize
      const u: User = {
        id: (data.id as string | number) ?? (data.user_id as string | number) ?? 0,
        email: (data.email as string) ?? (data.username as string) ?? "",
        role: ((data.role as string) ?? "customer") as UserRole,
      };
      setUser(u);
      localStorage.setItem("user", JSON.stringify(u));
    } catch {
      // fallback to token payload or stored user
      const payload = tok ? parseTokenPayload(tok) : null;
      if (payload?.email) {
        const fallback: User = {
          id: (payload.id as string | number) ?? user?.id ?? 0,
          email: payload.email as string,
          role: (payload.role as UserRole) ?? (user?.role as UserRole) ?? "customer",
        };
        // keep existing user if fetch fails but token exists
        if (!user) {
          setUser(fallback);
          localStorage.setItem("user", JSON.stringify(fallback));
        }
      }
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchMe(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
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
    // fetch me
    try {
      const meRes = await client.get("/auth/me", {
        headers: { Authorization: `Bearer ${tok}` },
      });
      const md = meRes.data as Record<string, unknown>;
      const u: User = {
        id: (md.id as string | number) ?? 0,
        email: (md.email as string) ?? email,
        role: ((md.role as string) ?? "customer") as UserRole,
      };
      setUser(u);
      localStorage.setItem("user", JSON.stringify(u));
    } catch {
      const payload = parseTokenPayload(tok);
      const u: User = {
        id: (payload?.id as string | number) ?? 0,
        email: (payload?.email as string) ?? email,
        role: (payload?.role as UserRole) ?? "customer",
      };
      setUser(u);
      localStorage.setItem("user", JSON.stringify(u));
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      await client.post("/auth/register", { email, password });
      // auto login
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setToken(null);
    setUser(null);
  }, []);

  const refreshMe = useCallback(async () => {
    const t = localStorage.getItem("token");
    setLoading(true);
    await fetchMe(t);
  }, [fetchMe]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, loading, login, register, logout, refreshMe }),
    [user, token, loading, login, register, logout, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
