# Shared Scripts

Bu dizin 3 ORBIS repo arası paylaşılan scriptleri içerir:

## sync-shared-js.sh
Flask (`orbisapp/static/js`) → Mobile (`orbis-mobile/mobile/www/js`) paylaşılan JS dosyalarını sync eder.

## Repolar
- **orbisapp** — Flask backend + PWA: `static/js/{mobile-bridge,firebase-config,admob-config}.js`
- **orbis-mobile** — Capacitor Android: `mobile/www/js/`
- **orbis-landing** — Statik tanıtım sitesi (bağımsız, sync yok)

## Neden paylaşım var
Capacitor WebView + PWA aynı JS bundle kullanıyor. Monorepo yerine pre-build sync seçtik — bağımsız deploy/rollback için.
