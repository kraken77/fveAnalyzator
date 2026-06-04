# NZÚ 2026 Kalkulačka — Bezúročný úvěr / NZÚ Light

Samostatná HTML kalkulačka pro výpočet maximální výše státní podpory v rámci programu Nová zelená úsporám 2026+.

## Popis

Kalkulačka simuluje výpočet dotací z programu NZÚ 2026 pro rodinné i bytové domy. Uživatel zadá typ budovy, plochy zateplení, vybraná OZE opatření a systém okamžitě vypočítá maximální výši bezúročného úvěru včetně rozpisu dle jednotlivých oblastí.

Výsledky lze využít jako vstup pro ekonomickou analýzu FVE v rámci hlavního projektu `fveAnalyzator`.

## Režimy (5)

| Režim | Popis | Max. úvěr |
|-------|-------|-----------|
| **RD — Komplexní opatření** | Úplná rekonstrukce zateplení + povinné OZE | 2 000 000 Kč |
| **RD — Dílčí opatření** | Individuální opatření bez komplexní renovace | 750 000 Kč |
| **RD — NZÚ Light** | Nízkopříjmoví žadatelé (4. decil), bonus 2 000 Kč/m² | 400 000 Kč |
| **BD — Komplexní renovace** | Celková rekonstrukce bytového domu | 750 000 Kč / b.j. |
| **BD — Dílčí renovace** | Individuální opravy v bytovém domě | 250 000 Kč / b.j. |

## Oblasti opatření

| Oblast | Popis | Sačba / limit |
|--------|-------|---------------|
| **A** | Zateplení (stěny, střecha, podlahy, okna) | 2 000–5 000 Kč/m² |
| **C.1** | Zdroj tepla (biomasa, tepelná čerpadla, CZT) | 100 000–400 000 Kč |
| **C.2** | Příprava teplé vody (solární, FV, TČ) | 100 000 Kč |
| **C.3** | Fotovoltaika + baterie | 25 000 Kč/kWp, 15 000 Kč/kWh |
| **C.4** | Větrání s rekuperací | 200 000 Kč |
| **C.5** | Teplo z odpadní vody | 100 000 Kč |
| **D.1** | Zelená střecha | 2 000 Kč/m², max 150 000 Kč |
| **D.2** | Dešťovka / šedá voda | 100 000–150 000 Kč |

## Památkově chráněná budova

Zaškrtnutí této volby navýší sazby: stěny 5 000 Kč/m², okna 18 000 Kč/m².

## 4. příjmový decil

Umožňuje splácet úvěr až 25 let (standardně 10–15 let).

## Použití

Stačí otevřít `index.html` v prohlížeči — žádný server ani instalace není potřeba.

1. Vybrat režim (klik na tlačítko nahoře)
2. Zadat plochy zateplení (m²)
3. Zaškrtnout požadovaná opatření
4. Výsledek se zobrazí vpravo — celková částka + rozpis dle oblastí

## Technické detaily

- **Technologie**: Vanilla JavaScript + Tailwind CSS (CDN)
- **Formát**: Single-file HTML (žádné externí závislosti kromě Tailwind CDN)
- **Data**: Sazby extrahované z originálu refsite.info (informativní)
- **Min. úvěr pro výpočet**: 100 000 Kč

## Licence

Stejná jako hlavní projekt `fveAnalyzator`.
