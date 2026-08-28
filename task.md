- [x] Analýza zadání @[Datová a ekonomická Analýza FVE Rabiav s.r.o. zadání.docx]
- [x] Inicializace projektu
  - [x] Vytvoření `README.md`
  - [x] Vytvoření `requirements.txt`
  - [x] Nastavení `docker-compose.yml`
- [x] Implementace `src/data_loader.py`
- [x] Implementace `src/analyzer.py`
- [x] Implementace `src/visualizer.py`
- [x] Implementace `src/app.py`
- [x] Testování a verifikace
- [x] Implementace stránky Ekonomika - Investice
  - [x] Rozšíření `src/analyzer.py` o investiční výpočty
  - [x] Rozšíření `src/visualizer.py` o grafy návratnosti
  - [x] Úprava `src/app.py` pro navigaci a novou stránku
- [x] Úprava UI (české formátování čísel)
- [x] Přidání scénáře FVE + Reinvestice úspor
- [x] Rozdělení ceny elektřiny (silová + distribuce)
- [x] Škálovatelný profil spotřeby (dle roční spotřeby)
- [x] Zobrazení energetických toků v kWh (Nákup/Prodej)
- [x] Detailní ekonomická bilance (CZK) pod energetickou bilancí
- [x] Koláčový graf složení úspor (Vlastní spotřeba vs Prodej)
- [x] Optimalizace rozložení dashboardu (Pie chart vedle metrik)
- [x] Treemap vizualizace úspor (Kategorie + Měsíce)
- [x] Úprava vizualizací (Treemap hierarchie, České měsíce, Layout)
- [x] Prohození sekcí (Data před Denní bilancí)
- [x] Energetické grafy úspor (Pie + Treemap v kWh)
- [x] Vylepšení koláčových grafů (Legenda + Hodnota + % uvnitř)
- [x] Formátování hodnot v grafech (CZ standard + Kč)
- [x] Formátování tabulek (České sloupce + Kč/kWh)
- [x] Přejmenování projektu na fveAnalyzator

## Generování PDF Reportu

- [x] Výzkum knihoven pro PDF (WeasyPrint, ReportLab, Streamlit export)
- [x] Implementace exportu grafů do obrázků
- [x] Vytvoření šablony reportu (HTML/CSS nebo canvas)
- [x] Integrace tlačítka "Stáhnout PDF" do aplikace
- [x] Zahrnutí všech dashboardů a tabulek do reportu
  - [x] Refactoring výpočtů pro dostupnost dat
  - [x] Přidání zbývajících grafů (Treemaps, Energy Pie, Daily, Investment)
  - [x] Přidání tabulek (Data, Investice)
  - [x] Úprava šablony reportu
- [x] Přidání tabulky vstupních parametrů na každou stránku reportu
- [x] Přidání specifické hlavičky pro Ekonomickou analýzu (S&P 500, Inflace)
- [x] Přesun legendy grafu investic pod graf (Streamlit + PDF)

## Implementace typů spotřebičů elektrické energie

- [x] Bazén
  - [x] Filtrace (spotřeba, RomanVaibar bazén 18m3, 6000l/h, 650W)
  - [x] Ohřev vody (porovnání ceny vs tepelné čerpadlo)
- [x] Bojler - příprava Teplé Užitkové Vody
  - [x] Velikost (200l, 300l, 500l, 1000l)
  - [x] Regulovatelné na dobu dostatečné elektrické energie z FVE
  - [x] RomanVaibar 300l topná spirála 3.5 kW
- [x] Sušička, Pračka (jeden společný spotřebič)
- [x] Sušička (samostatné spotřebiče)
- [x] Myčka (samostatné spotřebiče)
- [x] Elektrovozidlo - Jaecoo 7 (18.6kWh baterie)
  - [x] Nabíjení 1 fáze max 6kW
  - [x] Nabíjení RomanVaibar 1 fáze max 4.4kW (omezení na 20A jistič)
- [x] Elektrovozidlo - např. Enyaq (80kWh baterie)
  - [x] Nabíjení 3 fáze max 3*7.04kW 22kW wallbox (maximální jistič 32A)
  - [x] Nabíjení RomanVaibar 3 fáze max 3x4.4kW (omezení na 20A jistič)
- [x] Tepelné čerpadlo
- [x] Termální baterie (model baterie, uložení energie do vody/písku, velikost, investiční náklady, výdrž energie)

## Prodej přebytků z FVE

- [x] Omezení na možnost přetoků dle podmínek připojení
  - [x] Mělo by odpovídat na max. možnost výroby tedy počet panelů * výkon
  - [x] Nebo jasně definované podmínkami připojení RomanVaibar podmínky 14.2 kW
- [x] Přes komunitu - definované jednou sazbou např. 1.5Kč a kWh
- [x] Přes sdílení elektřiny - odpovídající ceně silové energie - částka zase definovaná např. 2.54 Kč/kWh
- [x] Přes spot ceny dle OTE hodnot kde se cena bere OTE cena - 0.4 Kč/1kWh pro obchodníka

## Omezení výkonu FVE

- [x] Dle umístění podle GPS pozice a umístění FVE vůči světovým stranám S, J, V, Z - najdi a připrav model který bude odebírat z maximálního výkonu
- [x] Dle sklonu střechy opět sklon střechy vůči ideálnímu sklonu
- [x] Rozdělení FVE dle panelů mohou být skupiny s různými počty panelů s umístěním - vytvoření

## Škálování FVE

- [x] Vypočet klidně i někokrát s různými počtem panelů baterií velikostí
- [x] Kolik je možné uložit z přetoků do Termální baterie

## Frontend Streamlit

- [x] Vytvoření adresáře `frontend-streamlit`
- [x] Vytvoření `app.py` v `frontend-streamlit`
- [x] Přidání `streamlit` do `requirements.txt`
- [x] Aktualizace `docker-compose.yml` pro spuštění Streamlit aplikace
- [x] Aktualizace `app.py` pro použití `BACKEND_URL` z proměnné prostředí

## Realističtější model PV výroby

- [x] Implementovat geocoding (převod adresy na GPS souřadnice)
- [x] Získat reálná meteorologická data (např. TMY data z PVGIS) pro dané GPS souřadnice
- [x] Upravit `pv_calculator.py` pro použití reálných meteorologických dat místo clear-sky modelu
- [x] Aktualizovat UI pro zadávání adresy a zobrazení relevantních informací o zdroji dat

## Spuštění a údržba

- [x] Spuštění projektu pomocí Docker Compose
