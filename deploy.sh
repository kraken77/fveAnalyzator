#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — nasazení AntelonEnergy na server (drakisa, https://fve.etikos.cz)
#
# Spouští se NA SERVERU v adresáři projektu (/home/roman/apps/antelon-energy):
#     ./deploy.sh
#
# Co skript dělá:
#   1. Zálohuje produkční data (data/reportgen.db) do data/backups/
#   2. Stáhne nejnovější kód z GitHubu (git pull --ff-only)
#   3. Znovupostaví a restartuje docker compose služby
#   4. Ověří zdraví backendu a webu
#
# POZOR: produční data (reportgen.db, data/projects, spot_market.db) žijí jen
# na disku serveru a NEJSOU v gitu — skript je proto před pull/buildem zálohuje.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$APP_DIR/data/backups"
WEB_PORT="${WEB_PORT:-3001}"

echo "==> [1/5] Záloha produkčních dat"
mkdir -p "$BACKUP_DIR"
if [ -f data/reportgen.db ]; then
  cp -a data/reportgen.db "$BACKUP_DIR/reportgen.db.$STAMP"
  echo "    zaloha: $BACKUP_DIR/reportgen.db.$STAMP"
else
  echo "    (reportgen.db neexistuje — nic k zálohování)"
fi

echo "==> [2/5] Stažení nejnovějšího kódu (git pull --ff-only)"
git pull --ff-only

echo "==> [3/5] Build + start kontejnerů"
docker compose up -d --build

echo "==> [4/5] Stav služeb"
docker compose ps

echo "==> [5/5] Healthcheck"
sleep 5
if curl -fsS "http://localhost:8051/docs" >/dev/null 2>&1; then
  echo "    backend  -> http://localhost:8051/docs ... OK"
else
  echo "    backend  -> NEDOSTUPNÝ (check docker compose logs -f)"
  exit 1
fi
if curl -fsS "http://localhost:${WEB_PORT}" >/dev/null 2>&1; then
  echo "    web      -> http://localhost:${WEB_PORT} ... OK"
else
  echo "    web      -> NEDOSTUPNÝ (check docker compose logs -f web)"
  exit 1
fi

echo "==> Hotovo."