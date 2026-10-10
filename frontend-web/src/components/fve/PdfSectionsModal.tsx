import { useEffect, useState } from "react";
import { fetchReportSections } from "../../api/fve";
import type { PdfVariant, ReportSectionMeta } from "../../types";

interface Props {
  variant: PdfVariant;
  /** Uložený výběr oddílů (id). Když chybí/prázdný, zapnou se všechny. */
  initial?: string[];
  onClose: () => void;
  /** Vrací seřazená id zapnutých oddílů (bez vypnutých). */
  onGenerate: (orderedIds: string[]) => void;
}

/**
 * Modální výběr oddílů PDF: zapnutí/vypnutí volitelných oddílů a změna
 * pořadí. Pevný základ (meta.base) je vždy zaškrtnutý a nejde vypnout.
 */
export default function PdfSectionsModal({
  variant,
  initial,
  onClose,
  onGenerate,
}: Props) {
  const [metas, setMetas] = useState<ReportSectionMeta[]>([]);
  const [order, setOrder] = useState<string[]>([]);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchReportSections()
      .then((ms) => {
        setMetas(ms);
        const ids = ms.map((m) => m.id);
        // Uložený výběr se použije, jen když obsahuje aspoň jedno známé id;
        // jinak (nové oddíly, prázdno) se zapne vše.
        const valid = (initial ?? []).filter((i) => ids.includes(i));
        const selected = valid.length ? valid : ids;
        setEnabled(new Set(selected));
        // Pořadí: nejdřív uložené, pak nové v kanonickém pořadí.
        setOrder([...selected, ...ids.filter((i) => !selected.includes(i))]);
      })
      .catch(() => {
        setMetas([]);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, [initial]);

  const move = (idx: number, dir: -1 | 1) => {
    const j = idx + dir;
    if (j < 0 || j >= order.length) return;
    // Rám (intro/slovník) je připnutý serverem — nedovol ho prohodit ani
    // přes šipku souseda, ať zobrazené pořadí odpovídá výstupu PDF.
    const isFrame = (id: string) => !!metas.find((m) => m.id === id)?.frame;
    if (isFrame(order[idx]) || isFrame(order[j])) return;
    const next = [...order];
    [next[idx], next[j]] = [next[j], next[idx]];
    setOrder(next);
  };

  const toggle = (id: string, fixed: boolean) => {
    if (fixed) return; // pevný základ ani rám nelze vypnout
    setEnabled((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const label = variant === "customer" ? "PDF pro zákazníka" : "PDF pro firmu";

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-5">
        <h3 className="text-lg font-semibold text-navy mb-1">{label} — oddíly</h3>
        <p className="text-sm text-slate-500 mb-4">
          Pevný základ i rám (úvod, slovníček) jsou vždy součástí a nejdou
          vypnout. Volitelné oddíly zapněte a šipkami upravte pořadí.
        </p>

        {loading && <p className="text-sm text-slate-400">Načítám oddíly…</p>}
        {error && !loading && (
          <p className="text-sm text-red-600">
            Nepodařilo se načíst oddíly. Obnovte stránku a zkuste to znovu.
          </p>
        )}

        <ul className="space-y-1">
          {order.map((id, idx) => {
            const meta = metas.find((m) => m.id === id);
            if (!meta) return null;
            const fixed = meta.base || !!meta.frame;
            const on = fixed || enabled.has(id);
            return (
              <li
                key={id}
                className="flex items-center gap-3 border-b border-slate-100 py-2"
              >
                <input
                  type="checkbox"
                  checked={on}
                  disabled={fixed}
                  onChange={() => toggle(id, fixed)}
                  className="h-4 w-4"
                />
                <div className="flex-1">
                  <div className="text-sm text-slate-800">
                    {meta.label}
                    {meta.base && (
                      <span className="text-xs text-slate-400 ml-2">
                        (pevný základ)
                      </span>
                    )}
                    {!meta.base && meta.frame && (
                      <span className="text-xs text-slate-400 ml-2">
                        (rám — pořadí serverem)
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500">{meta.description}</div>
                </div>
                {!meta.frame && (
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => move(idx, -1)}
                      disabled={idx === 0}
                      className="px-2 py-1 border rounded disabled:opacity-30"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => move(idx, 1)}
                      disabled={idx === order.length - 1}
                      className="px-2 py-1 border rounded disabled:opacity-30"
                    >
                      ↓
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        <div className="flex justify-end gap-3 mt-5">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm border rounded-lg"
          >
            Zrušit
          </button>
          <button
            type="button"
            onClick={() =>
              onGenerate(
                order.filter((i) => {
                  const m = metas.find((x) => x.id === i);
                  return enabled.has(i) || !!m?.base || !!m?.frame;
                }),
              )
            }
            disabled={loading || error}
            className="px-4 py-2 text-sm bg-antelonGreen text-navy font-semibold rounded-lg disabled:opacity-50"
          >
            Vygenerovat PDF
          </button>
        </div>
      </div>
    </div>
  );
}
