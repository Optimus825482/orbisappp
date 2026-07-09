#!/usr/bin/env bash
# sync-shared-js.sh
# ORBIS mimarisi: static/js/* Flutter WebView + Capacitor mobile webview tarafindan
# paylasilir. Tek kaynak: orbisapp/static/js/{mobile-bridge,firebase-config,admob-config}.js
# Bu script orbis-mobile build oncesi calistirilir.
#
# Kullanim:
#   ./sync-shared-js.sh <ORBISAPP_PATH> <ORBISMOBILE_PATH>
# Ornek:
#   ./sync-shared-js.sh ../orbisapp ../orbis-mobile/mobile/www
#
# CI entegrasyonu (orbis-mobile .github/workflows/build.yml):
#   - name: Sync shared JS
#     run: ../scripts-shared/sync-shared-js.sh ../orbisapp mobile/www

set -euo pipefail

ORBISAPP_PATH="${1:?Usage: $0 <ORBISAPP_PATH> <ORBISMOBILE_PATH>}"
ORBISMOBILE_PATH="${2:?Usage: $0 <ORBISAPP_PATH> <ORBISMOBILE_PATH>}"

SHARED_FILES=(
  "mobile-bridge.js"
  "firebase-config.js"
  "admob-config.js"
)

echo "[sync-shared-js] Source: $ORBISAPP_PATH/static/js"
echo "[sync-shared-js] Target: $ORBISMOBILE_PATH/js"

for f in "${SHARED_FILES[@]}"; do
  src="$ORBISAPP_PATH/static/js/$f"
  dst="$ORBISMOBILE_PATH/js/$f"

  if [ ! -f "$src" ]; then
    echo "  ✗ $f: source yok ($src)"
    continue
  fi

  mkdir -p "$(dirname "$dst")"
  cp -f "$src" "$dst"
  echo "  ✓ $f synced"
done

echo "[sync-shared-js] done"
