/** Label instance z build argu `VITE_APP_LABEL` (Dockerfile; default `prod`).
 *
 * Dev image se builduje s `VITE_APP_LABEL=dev` (docker-compose.yml) — podle
 * této hodnoty se v UI zobrazuje oranžový pas "Vývojová verze".
 */
export const APP_LABEL: string =
  (import.meta.env.VITE_APP_LABEL as string | undefined) ?? "prod";
