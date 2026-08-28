import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="bg-navy text-white sticky top-0 z-40 shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/projects" className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-antelonGreen flex items-center justify-center font-black text-navy text-sm">
              A
            </div>
            <span className="font-bold tracking-wide text-sm sm:text-base">
              ANTELON ENERGY s.r.o.
            </span>
            <span className="hidden sm:inline text-xs font-medium bg-white/10 px-2 py-1 rounded">
              ReportGen
            </span>
          </Link>

          <nav className="flex items-center gap-4 sm:gap-6">
            <Link to="/projects" className="text-sm font-medium hover:text-antelonGreen transition">
              Projekty
            </Link>
            {user?.role === "admin" && (
              <Link
                to="/admin"
                className="text-sm font-medium hover:text-antelonGreen transition"
              >
                Administrace
              </Link>
            )}
            {user ? (
              <div className="flex items-center gap-3">
                <div className="hidden sm:flex flex-col items-end leading-tight">
                  <span className="text-xs opacity-80">{user.email}</span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded bg-antelonGreen text-navy">
                    {user.role}
                  </span>
                </div>
                <span className="sm:hidden text-xs font-semibold px-2 py-0.5 rounded bg-antelonGreen text-navy">
                  {user.role}
                </span>
                <button
                  onClick={handleLogout}
                  className="text-sm bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded-lg transition"
                >
                  Odhlásit
                </button>
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
        © {new Date().getFullYear()} Antelon Energy s.r.o. — ReportGen
      </footer>
    </div>
  );
}
