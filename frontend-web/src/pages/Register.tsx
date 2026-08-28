import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError("Hesla se neshodují");
      return;
    }
    if (password.length < 6) {
      setError("Heslo musí mít alespoň 6 znaků");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await register(email, password);
      navigate("/projects");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      const msg = detail || (err instanceof Error ? err.message : "Registrace selhala");
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-navy">Registrace</h1>
          <p className="text-sm text-slateMuted mt-1">Vytvořte si účet zákazníka</p>
        </div>

        <form
          onSubmit={onSubmit}
          className="card p-6 sm:p-8 space-y-4 border-l-4 border-l-antelonGreen"
        >
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
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-antelonGreen"
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
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-antelonGreen"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-navy mb-1">Potvrzení hesla</label>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="••••••••"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-antelonGreen"
            />
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {busy ? "Vytvářím účet..." : "Zaregistrovat se"}
          </button>

          <p className="text-center text-sm text-slate-600">
            Již máte účet?{" "}
            <Link to="/login" className="text-navy font-semibold hover:underline">
              Přihlásit se
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
