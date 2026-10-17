# AGENTS.md

Interní nástroj Antelon Energy: FVE analýza + procesní pipeline zakázek.
Backend FastAPI (`backend/`), jediný klient React (`frontend-web/`).
Architektura, mapa endpointů a známé mezery: **`docs/architektura.md`** —
přečíst před větší změnou. `docs/superpowers/{specs,plans}/` drží návrhy a
implementační plány jednotlivých etap.

## Příkazy

Backend — z kořene repa, venv je v `./venv` (Python 3.11):

```bash
./venv/bin/python -m pytest tests/ -q                    # celá suita: 278 testů, ~8 min
./venv/bin/python -m pytest tests/reportgen/test_workflow.py -q   # jeden soubor

# Dev server — POZOR: `main.py` importuje `app.*`, takže z kořene s uvicorn
# NEfunguje (`uvicorn backend.main:app` spadne na ModuleNotFoundError).
# Musí se z adresáře backend/, nebo s PYTHONPATH:
cd backend && ../venv/bin/python -m uvicorn main:app --reload --port 8000
```

Frontend (`frontend-web/`, Node 20+):

```bash
npm test        # vitest + jsdom; testy *.test.tsx vedle zdrojů
npm run build   # tsc -b (typecheck) && vite build — hlavní brána frontendu
npm run lint    # oxlint; ~19 pre-existing warningů je normál, exit 0

# Dev server: vite proxy cílí defaultně na :8000, jinak musí odpovídat backendu
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8051 npm run dev
```

Celé prostředí: `docker compose up -d --build` → web `:3100` (`WEB_PORT` z `.env`,
navíc fixně `:3001`), API `:8051` + `/docs`.

## Produkce a nasazení

- Produkce běží **na tomto stroji** (drakisa, 192.168.119.167): https://fve.etikos.cz,
  reverse proxy → web `:3001`, API `:8051`.
- Živé kontejnery `antelon-energy-*` běží **z tohoto checkoutu** a backend má
  bind-mount `./data` → **`data/reportgen.db` jsou živá data**. Nic do nich
  nezapisovat ad-hoc a nepřepisovat; zálohy se dělají do `data/backups/`.
- Frontend bundle je zapečený v image → změna frontendu se projeví až po
  `docker compose up -d --build`. Backend je bind-mount → stačí
  `docker compose restart backend`.
- **Push/merge/deploy jen na výslovný pokyn uživatele.**
- `deploy.sh` + `/home/roman/apps/antelon-energy` (README) je stará cesta: `apps`
  je opuštěný zářijový checkout s vlastními nepushnutými commity a starými daty —
  aktuální produkce jede odsud, odsud se i (re)buildí.
- Sdílené odkazy/QR (`/p/{code}`) staví z `RG_PUBLIC_URL` — v produkci musí být
  `https://fve.etikos.cz` (compose default je `http://localhost`).

## Konvence

- Vše česky: UI texty i commit messages (lowercase, bez diakritiky, conventional
  prefix se scope, např. `fix(dispecink): ...`, `test(pv): ...`).
- Nikdy `git add -A` — stagovat explicitní soubory. `data/*.db*` a `.superpowers/`
  se necommitují (jsou gitignored).
- TDD: testy před implementací. Backend pytest, frontend vitest.
- Změna chování → aktualizovat i příslušný spec/plán v `docs/superpowers/` a
  `docs/architektura.md`, commituje se spolu s kódem.
- README je v detailech zastaralé (např. tvrdí, že frontend nemá test framework) —
  příkazy ber odsud.
- E2E testy v repu nejsou; UI se ověřuje jednorázovými Playwright skripty mimo
  repo (Playwright je v `requirements.txt`).

## Testovací záludnosti (backend)

- Používat výhradně souřadnice z `data/weather_cache.db`: Praha 50.0880/14.4208,
  Ústí n. L. 50.6607/14.03227, 50.7170082/13.9644984, Brno 49.2/16.6. Jiná
  lokalita jde na síť k PVGIS → test timeoutuje.
- Spotřební data se generují náhodně (záměrná volba, šum ~0.005 %) — neosazovat.
- Každý test dostává vlastní dočasnou SQLite; `tests/reportgen/conftest.py` řeší
  sys.path (`backend/`, `backend/app`) i testovací účty `*@test.local`. Testy
  nesmí sahat na `data/reportgen.db`.

## Plotly — tichý failure mód

`frontend-web/src/lib/plotly.ts` je ořezaný bundle s ruční registrací typů grafů.
Když backend začne generovat nový typ grafu, musí se doplnit do `Plotly.register([...])`,
jinak se graf v prohlížeči prostě nevykreslí a build ani testy to neohlásí.
Konzistenci hlídá `tests/test_plotly_traces.py`. Změny grafů vždy ověřit v prohlížeči.
