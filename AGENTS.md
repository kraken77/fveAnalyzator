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

Dvě instance (obě z tohoto checkoutu, sdílí `./data`):

```bash
docker compose up -d --build                             # vývoj: web :3001, API :8051
docker compose -f docker-compose.prod.yml up -d --build  # produkce: web :3100, API :8052
```

## Produkce a nasazení

- Produkce = compose projekt `antelon-prod` (`docker-compose.prod.yml`) na tomto
  stroji (drakisa, 192.168.119.167): web `:3100`, API `:8052`. Veřejně
  **https://fve.etikos.cz** (DNS → 109.202.78.51): TLS se terminuje na
  okrajové krabici 192.168.119.20 (nginx; Let's Encrypt wildcard certifikáty
  pro etikos.cz / drakisa.cz / rabiav.cz, ACME webroot přes Apache na portu 80).
  Fve vhost proxyuje web na `:3100` a `/api/` na `:8052` — tj. na produkci.
- Veřejný port 80 se forwarduje na `.20:80` (Apache); před migrací tam byl
  webif MikroTik routeru. `etikos-nginx` (`/home/roman/etikos/nginx/nginx.conf`,
  mimo repo) je teď jen LAN — není to veřejný vstup.
- Vývoj = projekt `antelon-energy` (`docker-compose.yml`): web `:3001`, API `:8051`
  (veřejně nevystavený). Vývojový backend je bind-mount (stačí restart);
  produkční backend mount nemá → nasazení = `docker compose -f docker-compose.prod.yml
  up -d --build` (kód se zapeče do image z aktuálního stavu checkoutu).
- **Obě instance sdílí živá data** `./data` → `data/reportgen.db` jsou živá
  produkční data. Nic do nich nezapisovat ad-hoc a nepřepisovat; zálohy se dělají
  do `data/backups/`.
- Frontend bundle je v image (dev i prod) → změna frontendu se projeví až po
  rebuildu příslušného stacku.
- **Push/merge/deploy jen na výslovný pokyn uživatele.**
- `deploy.sh` + `/home/roman/apps/antelon-energy` je stará opuštěná cesta
  (zářijový checkout, vlastní nepushnuté commity, stará data) — nepoužívat.
- Sdílené odkazy/QR (`/p/{code}`) staví z `RG_PUBLIC_URL`: prod default
  `https://fve.etikos.cz`, dev `http://localhost:3001`.

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
