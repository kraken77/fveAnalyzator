import { useState } from "react";
import { convertToOrder, saveAnalysis } from "../../api/fve";
import client from "../../api/client";
import type { FveContact, FveParams, SavedAnalysis } from "../../types";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateContact(
  c: FveContact,
): Partial<Record<keyof FveContact, string>> {
  const e: Partial<Record<keyof FveContact, string>> = {};
  if (c.name.trim().length < 2) e.name = "Zadejte jméno a příjmení";
  if (!EMAIL_RE.test(c.email.trim())) e.email = "Zadejte platný e-mail";
  if (c.phone.replace(/\D/g, "").length < 9) e.phone = "Telefon musí mít alespoň 9 číslic";
  return e;
}

interface Props {
  params: FveParams;
  /**
   * Uvnitř existujícího projektu: analýza se do něj zapíše, nevznikne nový.
   * Kontakt jde do parametrů analýzy, protože PUT /projects/{id}/params
   * řeší jen fve_params.
   */
  projectId?: number | string;
  /** Po uložení. Volitelné. */
  onSaved?: (saved: SavedAnalysis | null) => void;
}

export default function ContactStep({ params, projectId, onSaved }: Props) {
  const inProject = projectId !== undefined;

  const [contact, setContact] = useState<FveContact>({ name: "", email: "", phone: "" });
  const [projectName, setProjectName] = useState("");
  const [errors, setErrors] = useState<Partial<Record<keyof FveContact, string>>>({});
  const [saving, setSaving] = useState<"draft" | "order" | null>(null);
  const [serverError, setServerError] = useState("");
  const [saved, setSaved] = useState<SavedAnalysis | null>(null);
  const [savedInProject, setSavedInProject] = useState(false);

  const set = (key: keyof FveContact, value: string) => {
    setContact((c) => ({ ...c, [key]: value }));
    // chybu schováme hned, jakmile uživatel začne psát — ne až při submitu
    if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }));
  };

  const submit = async (asOrder: boolean) => {
    const found = validateContact(contact);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(asOrder ? "order" : "draft");
    setServerError("");
    try {
      if (inProject) {
        // existující zakázka: parametry a kontakt do fve_params
        await client.put(`/projects/${projectId}/params`, {
          fve_params: {
            ...params,
            contact_name: contact.name.trim(),
            contact_email: contact.email.trim(),
            contact_phone: contact.phone.trim(),
          },
        });
        setSavedInProject(true);
        onSaved?.(null);
        return;
      }

      const result = await saveAnalysis(params, contact, projectName.trim() || undefined);
      setSaved(result);
      if (asOrder) {
        await convertToOrder(result.id);
      }
      onSaved?.(result);
    } catch (e: any) {
      setServerError(e?.response?.data?.detail || "Uložení se nezdařilo");
    } finally {
      setSaving(null);
    }
  };

  if (savedInProject) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-5 space-y-2">
        <h3 className="font-semibold text-emerald-900">Uloženo do zakázky</h3>
        <p className="text-sm text-emerald-800">
          Parametry analýzy a kontakt jsou uložené v tomto projektu.
        </p>
      </div>
    );
  }

  if (saved) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-5 space-y-2">
        <h3 className="font-semibold text-emerald-900">Analýza uložena</h3>
        <p className="text-sm text-emerald-800">
          Kód pro sdílení: <strong>{saved.share_code}</strong>
        </p>
        {saved.customer_created && (
          <p className="text-sm text-emerald-800">
            Založili jsme vám přihlášení na {contact.email}. Nastavte si heslo při prvním
            přihlášení.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
      <div>
        <h3 className="font-semibold text-navy">Kontakt</h3>
        <p className="text-sm text-slate-600 mt-1">
          Bez kontaktu nemá analýza v dalších krocích smysl — potřebujeme vědět, komu
          výsledek patří.
        </p>
      </div>

      {serverError && (
        <p className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
          {Array.isArray(serverError)
            ? serverError.map((d: any) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ")
            : serverError}
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label className="block">
          <span className="text-sm text-slate-700">Jméno a příjmení *</span>
          <input
            type="text"
            value={contact.name}
            onChange={(e) => set("name", e.target.value)}
            className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm"
          />
          {errors.name && <span className="text-xs text-red-600">{errors.name}</span>}
        </label>

        <label className="block">
          <span className="text-sm text-slate-700">E-mail *</span>
          <input
            type="email"
            value={contact.email}
            onChange={(e) => set("email", e.target.value)}
            className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm"
          />
          {errors.email && <span className="text-xs text-red-600">{errors.email}</span>}
        </label>

        <label className="block">
          <span className="text-sm text-slate-700">Telefon *</span>
          <input
            type="tel"
            value={contact.phone}
            onChange={(e) => set("phone", e.target.value)}
            placeholder="+420 777 123 456"
            className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm"
          />
          {errors.phone && <span className="text-xs text-red-600">{errors.phone}</span>}
        </label>

        {!inProject && (
          <label className="block">
            <span className="text-sm text-slate-700">Název zakázky</span>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="volitelné"
              className="mt-1 w-full border border-slate-300 rounded px-3 py-2 text-sm"
            />
          </label>
        )}
      </div>

      <div className="flex flex-wrap gap-3 justify-end">
        <button
          type="button"
          onClick={() => submit(false)}
          disabled={saving !== null}
          className="border border-navy text-navy px-5 py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          {saving === "draft" ? "Ukládám…" : "Uložit jako rozpracovanou analýzu"}
        </button>
        {!inProject && (
          <button
            type="button"
            onClick={() => submit(true)}
            disabled={saving !== null}
            className="bg-antelonGreen text-navy font-semibold px-5 py-2.5 rounded-lg hover:brightness-110 disabled:opacity-50"
          >
            {saving === "order" ? "Vytvářím zakázku…" : "Vytvořit zakázku a pokračovat"}
          </button>
        )}
      </div>
    </div>
  );
}
