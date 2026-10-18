import { Link, useNavigate } from "react-router-dom";
import { useAuth, hasAnyRole } from "../context/AuthContext";
import RoleSwitcher from "./RoleSwitcher";
import { useEffect, useState } from "react";
import client from "../api/client";
import type { Notification } from "../types";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout, activeRole } = useAuth();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [showNotif, setShowNotif] = useState(false);
  const [showUser, setShowUser] = useState(false);

  const isCustomer = hasAnyRole(user, ["customer"]);
  const showMaterialy = hasAnyRole(user, ["admin", "antelon", "buyer", "warehouse"]);
  const showAdmin = hasAnyRole(user, ["admin"]);

  useEffect(() => {
    if (user && !isCustomer) {
      client
        .get("/notifications")
        .then((res) => setNotifications((res.data as Notification[]) || []))
        .catch(() => setNotifications([]));
    }
  }, [user, isCustomer]);

  const unread = notifications.filter((n) => !n.read).length;

  const markAllRead = async () => {
    try {
      await Promise.all(
        notifications
          .filter((n) => !n.read)
          .map((n) => client.post(`/notifications/${n.id}/read`)),
      );
      setNotifications(notifications.map((n) => ({ ...n, read: true })));
    } catch {
      // ignore
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="bg-navy text-white sticky top-0 z-40 shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to={isCustomer ? "/projects" : "/dispecink"} className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-antelonGreen flex items-center justify-center font-black text-navy text-sm">
              A
            </div>
            <span className="font-bold tracking-wide text-sm sm:text-base">
              ANTELON ENERGY s.r.o.
            </span>
            <span className="hidden sm:inline text-xs font-medium bg-white/10 px-2 py-1 rounded">
              Dispečink
            </span>
          </Link>

          <nav className="flex items-center gap-3 sm:gap-5">
            {!isCustomer && (
              <Link
                to="/dispecink"
                className="text-sm font-medium hover:text-antelonGreen transition"
              >
                Dispečink
              </Link>
            )}
            <Link to="/projects" className="text-sm font-medium hover:text-antelonGreen transition">
              {isCustomer ? "Moje projekty" : "Projekty"}
            </Link>
            {/* fveAnalysis je nástroj pro interní i zákazníka — proto je
                v jednom menu pro obě skupiny, ne za podmínkou. */}
            <Link
              to="/fve-analysis"
              className="text-sm font-medium hover:text-antelonGreen transition"
            >
              fveAnalysis
            </Link>
            {showMaterialy && (
              <Link to="/materialy" className="text-sm font-medium hover:text-antelonGreen transition">
                Materiály
              </Link>
            )}
            {showAdmin && (
              <Link to="/admin" className="text-sm font-medium hover:text-antelonGreen transition">
                Administrace
              </Link>
            )}

            {user ? (
              <div className="flex items-center gap-3">
                {!isCustomer && (
                  <div className="relative">
                    <button
                      onClick={() => {
                        setShowNotif((s) => !s);
                        if (!showNotif && unread > 0) {
                          // only refresh if opened fresh
                        }
                      }}
                      className="relative text-sm bg-white/10 hover:bg-white/20 w-8 h-8 rounded-lg flex items-center justify-center"
                      title="Notifikace"
                      data-testid="notif-bell"
                    >
                      🔔
                      {unread > 0 && (
                        <span className="absolute -top-1 -right-1 bg-antelonOrange text-navy text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                          {unread}
                        </span>
                      )}
                    </button>
                    {showNotif && (
                      <div className="absolute right-0 mt-2 w-80 bg-white text-navy rounded-lg shadow-xl border border-slate-200 z-50 max-h-96 overflow-auto">
                        <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100">
                          <p className="text-xs font-bold uppercase text-slateMuted">Notifikace</p>
                          {unread > 0 && (
                            <button onClick={markAllRead} className="text-xs text-antelonGreen hover:underline">
                              Přečteno
                            </button>
                          )}
                        </div>
                        {notifications.length === 0 ? (
                          <p className="text-sm text-slateMuted p-4">Žádné notifikace</p>
                        ) : (
                          notifications.slice(0, 30).map((n) => (
                            <div key={String(n.id)} className={`px-4 py-2 border-b border-slate-50 text-sm ${n.read ? "opacity-60" : ""}`}>
                              <p>{n.text}</p>
                              <p className="text-[10px] text-slate-400 mt-0.5">
                                {n.created_at ? new Date(n.created_at).toLocaleString("cs-CZ") : ""}
                              </p>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                )}

                <RoleSwitcher />
                {/* User menu — Changelog, O programu, Odhlásit (původní
                    samostatné tlačítko Odhlásit je v dropdownu). */}
                <div className="relative">
                  <button
                    onClick={() => setShowUser((s) => !s)}
                    className="flex items-center gap-2 rounded-lg bg-white/10 px-2 py-1.5 transition hover:bg-white/20"
                    data-testid="user-menu-btn"
                  >
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-antelonGreen text-[10px] font-black text-navy">
                      {(user.email[0] || "?").toUpperCase()}
                    </span>
                    <span className="hidden text-xs opacity-80 md:inline">{user.email}</span>
                    <span className="text-[10px] opacity-60">▾</span>
                  </button>
                  {showUser && (
                    <div className="absolute right-0 z-50 mt-2 w-64 rounded-lg border border-slate-200 bg-white text-navy shadow-xl">
                      <div className="border-b border-slate-100 px-4 py-2.5">
                        <p className="truncate text-sm font-semibold">{user.email}</p>
                        <p className="text-[10px] uppercase tracking-wide text-slateMuted">
                          {activeRole}
                        </p>
                      </div>
                      <div className="py-1">
                        <Link
                          to="/changelog"
                          onClick={() => setShowUser(false)}
                          className="block px-4 py-2 text-sm hover:bg-slate-50"
                          data-testid="user-menu-changelog"
                        >
                          📝 Changelog
                        </Link>
                        <Link
                          to="/o-programu"
                          onClick={() => setShowUser(false)}
                          className="block px-4 py-2 text-sm hover:bg-slate-50"
                          data-testid="user-menu-about"
                        >
                          ℹ️ O programu
                        </Link>
                      </div>
                      <div className="border-t border-slate-100 py-1">
                        <button
                          onClick={() => {
                            setShowUser(false);
                            handleLogout();
                          }}
                          className="w-full px-4 py-2 text-left text-sm hover:bg-slate-50"
                          data-testid="user-menu-logout"
                        >
                          🚪 Odhlásit
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link to="/login" className="text-sm font-medium hover:text-antelonGreen">
                  Přihlášení
                </Link>
                <Link
                  to="/register"
                  className="text-sm bg-antelonGreen text-navy font-semibold px-3 py-1.5 rounded-lg hover:brightness-110"
                >
                  Registrace
                </Link>
              </div>
            )}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        {children}
      </main>
      <footer className="border-t bg-white py-4 text-center text-xs text-slate-500">
        © {new Date().getFullYear()} Antelon Energy s.r.o. — ReportGen / Dispečink
      </footer>
    </div>
  );
}