import { APP_LABEL } from "../lib/appEnv";

/** Oranžový pas "Vývojová verze" — vykreslí se jen na dev instanci
 * (build arg `VITE_APP_LABEL=dev`, viz `src/lib/appEnv.ts`).
 * Prod image (default `prod`) komponenta vrací null. */
export default function DevBanner() {
  if (APP_LABEL !== "dev") return null;
  return (
    <div
      data-testid="dev-banner"
      className="bg-[#f28e2b] px-4 py-1.5 text-center text-xs font-bold uppercase tracking-wide text-white"
    >
      Vývojová verze — dev instance (localhost:3100)
    </div>
  );
}
