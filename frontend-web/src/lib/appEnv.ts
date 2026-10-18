/** Label instance z build argu `VITE_APP_LABEL` (Dockerfile; default `prod`).
 *
 * Dev image se builduje s `VITE_APP_LABEL=dev` (docker-compose.yml) — podle
 * této hodnoty se v UI zobrazuje oranžový pas "Vývojová verze".
 */
export const APP_LABEL: string =
  (import.meta.env.VITE_APP_LABEL as string | undefined) ?? "prod";

/** Git SHA buildu (Dockerfile ho injectuje do `VITE_BUILD_SHA`; mimo Docker "—"). */
export const BUILD_SHA: string =
  (import.meta.env.VITE_BUILD_SHA as string | undefined) ?? "—";

/** Čas buildu UTC (Dockerfile ho injectuje do `VITE_BUILD_DATE`; mimo Docker "—"). */
export const BUILD_DATE: string =
  (import.meta.env.VITE_BUILD_DATE as string | undefined) ?? "—";
