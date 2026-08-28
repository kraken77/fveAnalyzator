# ReportGen — multi-template generátor PDF reportů

**Datum:** 2026-08-28
**Status:** schváleno uživatelem (2026-08-28)
**Repo:** AntelonEnergy (fveAnalyzator) — nový modul `backend/app/reportgen/` + `frontend-web/`

## 1. Cíl

Webová aplikace jako nový modul fveAnalyzator pro generování zákaznických PDF reportů:

- **Šablona Antelon** (styl Pentagon v2, 11 stran, 16:9) — z dat Shelly datalogeru (denní spotřeba Wh na fázi + Total, volitelně napětí a hodinový/15min profil).
- **Šablony fveAnalyzator** — wrap existujících reportů Energy/Economic/OTE (WeasyPrint + Jinja2 + Plotly).

Aplikace ukládá projekty, podporuje více rolí, teaser/blur pro nezákazníky a vodotisk pro anonymní PDF.

## 2. Rozhodnutí z brainstormingu

| Téma | Volba |
|------|-------|
| Účel | Mezi A a C — multi-template (Antelon + fveAnalyzator), A+C |
| Vstupy Antelon | C — denní agregace + hodinový/15min profil pokud je |
| Šablona fveAnalyzator | A — wrapping existujících modulů, nemigrovat kód |
| Stack | C — React (Vite TS) + FastAPI, Docker Compose, GitHub, server |
| Nahrávání CSV | C — jeden i více (více měsíců = sloučení + validace) |
| Editovatelnost Antelon | C — každý textový blok + volba sekcí |
| Persistence | B — SQLite projekty + historie verzí PDF |
| Rozsah fve V1 | A — Energy + Economic + OTE |
| Auth | 2 → rozšířeno na 4 role (viz níže) |
| Umístění | Nový modul v repo fveAnalyzator |

Paleta z Pentagon PDF: navy `#0b1f33`, zelená `#2fbf71`, oranžová `#f28e2b`, šedá `#566472`, bílý podklad, accent lišty na KPI kartách.

Formát PDF Antelon: 960×540pt (16:9 landscape), cover tmavý, content bílý.

Shell CSV: UTF-8 s BOM, bloky s titulkem + `Time, V` / `Čas, Wh`, datum `dd/mm/yyyy HH:MM`, tečka, `0` = chybějící.

## 3. Architektura

```
AntelonEnergy/
  backend/
    main.py                      # + include_router reportgen
    app/
      reportgen/
        __init__.py
        router.py                # /api/v1/*
        models.py                # Pydantic + SQLAlchemy modely
        storage.py               # SQLite reportgen.db + FS
        auth.py                  # JWT, hash, dependencies
        shelly_parser.py         # parser bloků
        antelon.py               # analytika Antelon
        templates_antelon/
          report.html            # Jinja2 → WeasyPrint
          styles.css
        fve_wrap.py              # volání analyzer.py + reporting.py
        photos.py                # upload
        qr.py                    # QR generování
        pdf_utils.py             # watermark, teaser blur
  frontend-web/                  # Vite + React 19 + TS + Tailwind
    src/
      pages/  Login, Register, Projects, ProjectDetail, PublicPreview
      components/
      api/
  docker-compose.yml             # + service web (nginx)
  data/                          # spot_market.db + reportgen.db + projects/{id}/
```

Stávající `frontend-streamlit` a `frontend/` (CRA skeleton) zůstávají.

## 4. Role a přístup

| Role | DB hodnota | Práva |
|------|-----------|-------|
| admin | `admin` | vše + správa uživatelů + správa spotřebičů (CRUD, zneplatnění) |
| antelon | `antelon` | všechny projekty (CRUD), edit parametrů/textů, fotky, čistý PDF, vytváření share kódu |
| customer | `customer` | jen projekty kam se připojil, vidí dle visibility, čistý PDF |
| anonymous | — | jen teaser náhled přes `/p/{code}`, PDF s vodotiskem |

Hierarchie: admin ⊃ antelon ⊃ customer ⊃ anonymous.

## 5. Onboarding zákazníka

1. Zákazník self-registrace (email+heslo).
2. Zaměstnanec vytvoří projekt → `share_code` (8 znaků) + URL `/p/{code}` + QR PNG.
3. Zákazník scanne/otevře odkaz → „Připojit se k projektu" → záznam v `project_users`.
4. Anonym na `/p/{code}` vidí teaser + CTA „Vytvořit účet".

## 6. Data model (SQLite `data/reportgen.db`)

- `users(id, email UNIQUE, password_hash, role, created_at)`
- `projects(id, name, customer_name, description, owner_id, share_code UNIQUE, antelon_params_json, fve_params_json, created_at, updated_at)`
- `project_users(project_id, user_id, joined_at, PK composite)`
- `project_files(id, project_id, kind, filename, path, uploaded_at)`
  - kind: `consumption_daily`, `voltage`, `profile_15min`
- `project_photos(id, project_id, filename, path, caption, position, uploaded_at)`
- `pdf_versions(id, project_id, template, version, audience, file_path, params_snapshot_json, created_by, created_at)`

`antelon_params_json` obsahuje: title, subtitle, variants A/B/C, per-section {enabled, text}, visibility overrides, brand.

## 7. Shelly parser

- Detekce BOM, rozdělení na bloky podle titulku.
- Titulky: `Fáze A/B/C` (spotřeba, `Čas, Wh`), `phase A/B/C min/max voltage` (`Time, V`), `Total`/`Celkem` (pokud existuje → preferováno pro KPI).
- Datum parse `dd/mm/yyyy HH:MM`, float s tečkou, `0` → None/missing.
- Merge více souborů: union dle data, duplikát = chyba s výčtem.
- Kompletní dny: vnitřní dny kde všechny očekávané fáze mají non-missing; první+poslední den období = neúplný; seznam mezer.
- Output: `{blocks: [{metric, phase, df}], gaps, complete_days, warnings}`.

## 8. Antelon analytika (deterministická)

Vstup: denní Total + per-fáze, volitelně profile_df (hourly/15min).

Výstupy:
- `n_complete`, `total_kwh`, `avg_daily_kwh`, `annual_mwh = avg*365/1000`, `weekday_avg`, `weekend_avg` (kalendářní split).
- `phase_pct {A,B,C}`.
- Model spotřeba↔výroba:
  - Pokud profile_df existuje → průměrný pracovní den z profilu.
  - Jinak model typického dne: denní spotřeba rozprostřena dle šablony denního průběhu; výroba FVE: denní energie = kWp * `yield_per_kwp_per_day` (default 4.5 kWh/kWp v létě), hodinový tvar zvon (6–20h).
- `green_kwh = sum(max(prod-cons,0))`, `red_kwh`, `net_surplus`, `fve_daily_kwh`.
- Simulace baterie: kapacity 15/20kWh, SoC min 30%, start 100%, charge z přebytku, discharge na deficit, track SoC.
- Varianty: 20/25/30 kWp → roční výroba `kWp*1000`.

## 9. Šablona Antelon PDF

- Jinja2 `templates_antelon/report.html` + `styles.css` → WeasyPrint 960×540pt.
- Sekce (dle Pentagon v2): cover, 1 summary KPI, 2 pracovní vs víkend, 3 fázové zatížení, 4 doporučené řešení, 5 spotřeba vs výroba, 5b zelená/červená, 6 bilance, 7 baterie, 8 varianty, 9 doporučení, volitelně foto.
- Každá sekce: `enabled`, editable titulky/texty s placeholdery `{avg_daily_kwh}` apod., `visibility: full|teaser|internal`.
- Grafy: matplotlib PNG → base64 (barvy navy/zelená/oranžová).
- Teaser PDF: pro `teaser` sekce PNG detailu se rozostří (PIL GaussianBlur) + overlay „Zpracováno — dostupné po připojení".
- Vodotisk anonym: diagonální `NÁVRH — KONFIDENCIÁLNÍ` přes celý PDF (reportlab overlay nebo WeasyPrint background).

## 10. fveAnalyzator wrap

- `fve_wrap.py` importuje `analyzer.calculate_*` a `reporting.ReportGenerator` interně (ne HTTP).
- `POST /analysis/energy` logika extrahována do sdílené funkce volané oběma routery.
- Endpointy reportgen delegují: energy→load_consumption mock zůstává, ale přijímá `annual_consumption_mwh` z fve_params; production z PVGIS; atd.
- OTE: `GET /ote/status`, `POST /ote/update` (jen antelon/admin).

## 11. API (`/api/v1`)

- `POST /auth/register {email,password}` → customer
- `POST /auth/login {email,password}` → JWT
- `GET /auth/me`
- `GET /projects`, `POST /projects`, `GET /projects/{id}`, `PUT /projects/{id}`, `DELETE /projects/{id}`
- `POST /projects/{id}/share` → `{code, url, qr_b64}`
- `POST /public/join {code}` (auth), `GET /public/p/{code}` → teaser data
- `POST /projects/{id}/files` (multipart, multiple), `GET /projects/{id}/files`, `DELETE /projects/{id}/files/{fid}`
- `POST /projects/{id}/photos`, `GET /projects/{id}/photos`, `DELETE`
- `GET /projects/{id}/data` → parsed preview + KPI
- `PUT /projects/{id}/params {antelon_params?, fve_params?}`
- `POST /projects/{id}/generate {template: antelon|energy|economic|ote}` → pdf_version
- `GET /projects/{id}/pdfs`, `GET /projects/{id}/pdfs/{vid}/download?mode=full|teaser` (RBAC)
- `GET /ote/status`, `POST /ote/update`
- `GET /admin/appliances`, `PUT /admin/appliances/{name}` (admin, is_active flag)

JWT HS256, secret z env `RG_JWT_SECRET`, 7d expiry, `Authorization: Bearer`.

## 12. Frontend-web

- Vite + React 19 + TS + Tailwind + React Router + TanStack Query.
- Stránky: `/login`, `/register`, `/projects`, `/projects/:id` (tabs: Data | Parametry | Náhled | PDF | Fotky | Sdílení), `/p/:code` (public teaser, blur CSS, CTA registrace, watermarked download).
- Public teaser: viditelné KPI + seznam sekcí, zbytek `filter: blur(6px)` + badge, po vzorcích laditelné (visibility config).
- Build → nginx, proxy `/api/` → backend.

## 13. Docker

- `web` service: multi-stage `node:20` build → `nginx:alpine`, `nginx.conf` proxy `/api/` → `backend:8000`.
- `backend` beze změny (port 8050→8000), volume `./data` + `./backend:/app` dev, env `RG_JWT_SECRET`, `RG_ADMIN_EMAIL/PASSWORD` (auto-seed admin).
- `frontend-streamlit` ponechán.
- Nové deps: `matplotlib`, `qrcode[pil]`, `python-jose[cryptography]`, `passlib[bcrypt]`, `pillow`.

## 14. Testy

- `tests/reportgen/test_parser.py` — BOM, bloky, nuly, merge, kompletní dny.
- `tests/reportgen/test_antelon.py` — fixture Shelly-Wh syntetický → ověř KPI.
- `tests/reportgen/test_auth.py` + `test_api.py` (TestClient).
- E2E Playwright: login→create→upload→params→generate→download, public teaser.
- Regrese: stávající `pytest` musí projít.

## 15. Milníky

M1 parser+DB+auth → M2 analytika+PDF → M3 wrap fve → M4 frontend core → M5 role/teaser/watermark/QR/fotky → M6 docker+E2E+README.

## 16. Rizika

- matplotlib fonty, WeasyPrint blur overlay, CWD závislé `data/` cesty, `frontend/` CRA skeleton ignorovat.
