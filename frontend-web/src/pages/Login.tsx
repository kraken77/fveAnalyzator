import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate("/projects");
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : // eslint-disable-next-line @typescript-eslint/no-explicit-any
            ((err as any)?.response?.data?.detail as string) || "Přihlášení selhalo";
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      setError(detail || msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-navy">Přihlášení</h1>
          <p className="text-sm text-slateMuted mt-1">Zadejte e-mail a heslo pro vstup do ReportGen</p>
        </div>

        <form onSubmit={onSubmit} className="card p-6 sm:p-8 space-y-4 border-l-4 border-l-antelonGreen">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-navy mb-1">E-mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="vas@email.cz"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-antelonGreen focus:border-antelonGreen"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-navy mb-1">Heslo</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-antelonGreen focus:border-antelonGreen"
            />
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full btn-navy disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {busy ? "Přihlašuji..." : "Přihlásit se"}
          </button>

          <p className="text-center text-sm text-slate-600">
            Nemáte účet?{" "}
            <Link to="/register" className="text-antelonGreen font-semibold hover:underline">
              Zaregistrovat se
            </Link>
          </p>
        </form>

        <p className="text-center text-xs text-slate-400 mt-4">
          Demo přístup: admin / antelon / customer role dle registrace
        </p>
      </div>
    </div>
  );
}
