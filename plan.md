# Plán Projektu: fveAnalyzator (Analýza FVE)

## Cíl

Vytvořit komplexní nástroj pro hloubkovou analýzu realizace fotovoltaické elektrárny (FVE), optimalizaci jejího návrhu, porovnání s investičními alternativami a generování detailních reportů. Zahrnout realistické modely výroby FVE a flexibilní ekonomické scénáře.

## Fáze

1. **Příprava a Analýza**
   - [x] Analýza zadání
   - [x] Příprava struktury projektu
   - [x] Definice datových vstupů

2. **Implementace Jádra (Backend FastAPI)**
   - [x] Modul pro načítání dat (spotřeba, výroba, ceníky)
   - [x] Výpočetní modul (energetické toky, bilance, ztráty, baterie)
   - [x] Ekonomický modul (ROI, NPV, porovnání s S&P500)
   - [x] Správa spotřebičů (sezónní, regulovatelné)

3. **Frontend Streamlit**
   - [x] Vytvoření multi-stránkové aplikace
   - [x] Formuláře pro vstup parametrů
   - [x] Zobrazení výsledků energetické a ekonomické analýzy
   - [x] Funkce pro ukládání a načítání nastavení
   - [x] Formátování čísel a názvů pro CZ standard

4. **Model PV Výroby**
   - [x] Základní model výroby FVE (clear-sky)
   - [x] Implementace systémových a zimních ztrát FVE

5. **Rozšíření Datové Integrace (OTE & Spotové ceny)**
   - [x] Automatické stahování dat OTE (2023-2026)
   - [x] ETL proces pro uložení do DB (SQLite)
   - [x] Integrace spotových a flexibilních cenových schémat do výpočtů bilance

6. **Vizualizace a Reporting**
   - [x] Implementace grafů pomocí Plotly
   - [x] Generování detailních PDF reportů

7. **Dokumentace a Finalizace**
   - [x] Kompletace `README.md`
   - [x] Testování a ladění Docker prostředí
   - [ ] Další optimalizace a vylepšení
