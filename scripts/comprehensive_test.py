"""
ORBIS Comprehensive Test Suite
Tum sistem fonksiyonlarini basit bir sekilde test eder.
"""

import os, sys, json, re

PROJECT = "D:/astro-ai-predictor/backend/flask_app"
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

PASS = 0
FAIL = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    ok = condition() if callable(condition) else condition
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        ERRORS.append(f"  ❌ {name}" + (f" - {detail}" if detail else ""))
        print(f"  ❌ {name}" + (f" - {detail}" if detail else ""))


print("=" * 60)
print("ORBIS COMPREHENSIVE TEST SUITE")
print("=" * 60)

# ═══════════════════════════════════════════════════════
# 1. BACKEND IMPORT TEST
# ═══════════════════════════════════════════════════════
print("\n📦 1. BACKEND IMPORT TEST")

try:
    from __init__ import create_app
    app = create_app()
    test("Flask app olusturulabiliyor", True)
except Exception as e:
    test("Flask app olusturulabiliyor", False, str(e)[:100])

# Routes
try:
    from routes.main import bp
    test("main routes import", True)
except Exception as e:
    test("main routes import", False, str(e)[:80])

try:
    from routes.admin import admin_bp
    test("admin routes import", True)
except Exception as e:
    test("admin routes import", False, str(e)[:80])

try:
    from routes.push_routes import push_bp
    test("push routes import", True)
except Exception as e:
    test("push routes import", False, str(e)[:80])

# Services
for mod_name, mod_path in [
    ("firebase_service", "services.firebase_service"),
    ("ai_service", "services.ai_service"),
    ("stats_counter", "services.stats_counter"),
    ("astro_service", "services.astro_service"),
    ("chart_db_service", "services.chart_db_service"),
    ("location_service", "services.location_service"),
]:
    try:
        exec(f"from {mod_path} import *")
        test(f"{mod_name} servis import", True)
    except Exception as e:
        test(f"{mod_name} servis import", False, str(e)[:80])

try:
    from monetization.usage_tracker import UsageTracker
    from monetization.subscription import SubscriptionService
    test("monetization modul import", True)
except Exception as e:
    test("monetization modul import", False, str(e)[:80])

# ═══════════════════════════════════════════════════════
# 2. ROUTE COUNT & SECURITY
# ═══════════════════════════════════════════════════════
print("\n🔐 2. ROUTE & AUTH TEST")

rules = [r for r in app.url_map._rules]
route_count = len(rules)
test("Route sayisi > 50", route_count > 50, f"{route_count} adet")

# Admin endpoints should be behind /admin/
admin_routes = [r.rule for r in rules if '/admin/' in r.rule and 'api/' in r.rule]
test("Admin API route'lar var", len(admin_routes) > 5, f"{len(admin_routes)} adet")

# No open push-send endpoints
open_send = [r.rule for r in rules if 'push' in r.rule and 'send' in r.rule and '/admin/' not in r.rule]
test("Push send acik endpoint yok", len(open_send) == 0, f"{open_send}" if open_send else "")

# Pricing API exists
has_pricing = any('/api/config/pricing' in r.rule for r in rules)
test("/api/config/pricing mevcut", has_pricing)

# Health check
has_health = any('/api/health' in r.rule for r in rules)
test("/api/health mevcut", has_health)

# Heartbeat API
has_hb = any('/api/stats/heartbeat' in r.rule for r in rules)
test("/api/stats/heartbeat mevcut", has_hb)

# User login tracking
has_login = any('/api/stats/user-login' in r.rule for r in rules)
test("/api/stats/user-login mevcut", has_login)

# ═══════════════════════════════════════════════════════
# 3. MONETIZATION - KULLANIM TAKIBI
# ═══════════════════════════════════════════════════════
print("\n💰 3. MONETIZATION TEST")

from monetization.usage_tracker import UsageTracker
tracker = UsageTracker()

# can_use_feature returns requires_ad for free users
ut_src = open('monetization/usage_tracker.py').read()
can_use_block = ut_src.split('def can_use_feature')[1].split('def record_usage')[0]

test("5 dk kurali kalkti (last_ad_watch yok)", 'last_ad_watch' not in can_use_block)

# Her istek requires_ad dondurur
test("requires_ad True donduruyor", 'requires_ad' in can_use_block)
test("remaining: requires_ad", 'requires_ad' in can_use_block.split("remaining")[1].split(",")[0] if len(can_use_block.split("remaining")) > 1 else False)

# Admin/Premium override
is_admin_check = 'is_admin' in can_use_block
test("Admin override kontrolu var", is_admin_check)
is_premium_check = 'is_premium' in can_use_block
test("Premium override kontrolu var", is_premium_check)

# Subscription plans
sub = SubscriptionService()
plans = sub.get_plans()
test("Subscription planlar yukleniyor", len(plans) >= 3)
monthly = plans.get('premium_monthly', {})
test("Aylik fiyat > 0", monthly.get('price', 0) > 0)
test("Daily plan var", 'premium_daily' in plans)
test("Yearly plan var", 'premium_yearly' in plans)

# ═══════════════════════════════════════════════════════
# 4. MOBILE-BRIDGE JS KONTROLLERI
# ═══════════════════════════════════════════════════════
print("\n📱 4. MOBILE BRIDGE JS TEST")

mb = open('static/js/mobile-bridge.js').read()

# AdMob event isimleri plugin ile uyumlu
test("safeResolve var (cift-cagri korumasi)", 'safeResolve' in mb)
test("30s timeout guvenligi", 'timeoutId' in mb and '30000' in mb)
test("FailedToShow listener", 'onRewardedVideoAdFailedToShow' in mb)
test("FailedToLoad listener", 'onRewardedVideoAdFailedToLoad' in mb)
test("onRewardedVideoAdReward listener", 'onRewardedVideoAdReward' in mb)
test("onRewardedVideoAdDismissed listener", 'onRewardedVideoAdDismissed' in mb)

# Premium akisi
premium_section = mb.split('// Premium kullanici')[1].split('// Ucretsiz kullanici')[0] if '// Premium kullanici' in mb and '// Ucretsiz kullanici' in mb else ''
test("Premium credits-- KALKMIS", 'credits--' not in premium_section)

# resetToLocal premium'u sifirlar
test("resetToLocal premium false yapar", 'this.state.isPremium = false' in mb)

# verifyPremiumWithBackend
test("verifyPremiumWithBackend var", 'verifyPremiumWithBackend' in mb)

# confirm dialog kalkti
test("confirm dialog kalkti (Android WebView)", 'showAdConfirmDialog' not in mb)

# OrbisRewardedAds kopya kod yok
test("OrbisRewardedAds kopyasiz", '_showRewardedAd' not in mb)

# CONFIG ADMOB ID'leri
has_test = 'ADMOB_TEST' in mb and '3940256099942544' in mb
test("AdMob test ID'leri var", has_test)
has_prod = 'ADMOB_PROD' in mb and '2444093901783574' in mb
test("AdMob production ID'leri var", has_prod)

# Premium packages - 3 tane
pkg_count = mb.count("{ id:") 
test("Premium paket tanimli", pkg_count >= 3)

# Heartbeat
test("startHeartbeat fonksiyonu", 'startHeartbeat' in mb)
test("stopHeartbeat fonksiyonu", 'stopHeartbeat' in mb)
test("_sendHeartbeat fonksiyonu", '_sendHeartbeat' in mb)

# Firebase config'de de heartbeat
fc = open('static/js/firebase-config.js').read()
test("Firebase config heartbeat baslatma", 'startHeartbeat' in fc)
test("Firebase config user-login API cagrisi", '/api/stats/user-login' in fc)
test("Firebase config user-created API cagrisi", '/api/stats/user-created' in fc)
test("Firebase config stopHeartbeat (cikis)", 'stopHeartbeat' in fc)

# ═══════════════════════════════════════════════════════
# 5. AI SERVICE
# ═══════════════════════════════════════════════════════
print("\n🤖 5. AI SERVICE TEST")

ai_src = open('services/ai_service.py').read()
test("Firestore provider okuma", '_get_providers_from_firestore' in ai_src)
test("Fallback zinciri olusturma", '_get_fallback_chain' in ai_src)
test("Env fallback", '_get_env_fallback_chain' in ai_src)
test("Sira ile failover deneme", 'for i, provider in enumerate(fallback_chain)' in ai_src)
test("AKTIF/YEDEK loglama", 'tag' in ai_src.split('for i, provider')[1].split('call_provider')[0] if 'for i, provider' in ai_src else False)

# ═══════════════════════════════════════════════════════
# 6. TEMPLATELER
# ═══════════════════════════════════════════════════════
print("\n🖼️ 6. TEMPLATE TEST")

# Dashboard HTML temiz
dash = open('templates/admin/dashboard.html').read()
dash_divs = dash.count('<div') 
dash_divs_close = dash.count('</div>')
test("Dashboard HTML div dengeli", dash_divs == dash_divs_close, f"{dash_divs} acik, {dash_divs_close} kapali")
test("Dashboard eski kredi ID'si yok", 'stat-total-credits' not in dash)
test("Dashboard eski avg ID'leri yok", 'stat-avg-credits' not in dash)
test("Dashboard online kullanici karti var", 'stat-online-count' in dash)
test("Dashboard son login karti var", 'last-login-name' in dash)
test("Dashboard loadOnlineUsers var", 'loadOnlineUsers' in dash)
test("Dashboard 30sn interval var", '30000' in dash.split('setInterval')[1].split(')')[0] if 'setInterval' in dash else False)

# JS ID'leri HTML'de var
js_ids = re.findall(r'getElementById\("([^"]+)"\)', dash)
html_ids = re.findall(r'id="([^"]+)"', dash)
test(f"Dashboard JS ID'leri HTML'de mevcut ({len(js_ids)})", all(id in html_ids for id in js_ids), f"Eksik: {[id for id in js_ids if id not in html_ids]}")

# new_result.html
nr = open('templates/new_result.html').read()
test("Sonuc sayfasi 'Reklam izleyerek' mesaji", 'Reklam izleyerek' in nr)
test("Sonuc sayfasi premium modal var", 'premium-purchase-modal' in nr)
ai_comment_section = nr.split('// Kalan yorum durumunu')[1].split('//')[0] if '// Kalan yorum durumunu' in nr else ''
test("AI yorum 'hak kaldı' mesaji YOK", 'hak kald' not in ai_comment_section)

# Onboarding modal
onb = open('templates/components/premium_onboarding_modal.html').read()
test("Onboarding modal Premium Ayrıcalıkları butonu", 'Premium Ayrıcalıkları' in onb)
test("Onboarding modal Devam Et linki", 'Devam Etmek İçin Tıkla' in onb)
test("Onboarding premium detay gizli baslar", 'onboarding-premium-details' in onb)
test("showPremiumDetails fonksiyonu", 'showPremiumDetails' in onb)
test("hidePremiumDetails fonksiyonu", 'hidePremiumDetails' in onb)
test("Onboarding animate-bounce kalkti", 'animate-bounce' not in onb)
test("Onboarding IAP fallback OrbisBridge'e", 'OrbisBridge.purchasePremium' in onb)

# Landing page
lp = open('orbis-landing/index.html').read()
test("Landing page title", 'ORBIS' in lp)
test("Landing page Google Analytics", 'G-W61PWFWFMS' in lp)

# PWA manifest
manifest = json.load(open('static/manifest.json'))
test("PWA manifest short_name", manifest.get('short_name') == 'ORBIS')
test("PWA manifest display standalone", manifest.get('display') == 'standalone')
test("PWA manifest icons var", len(manifest.get('icons', [])) >= 5)
test("PWA manifest shortcuts var", len(manifest.get('shortcuts', [])) >= 1)
test("PWA manifest related_applications Play Store", len(manifest.get('related_applications', [])) >= 1)

# Admin pricing template
pr = open('templates/admin/pricing.html').read()
test("Admin pricing fiyat alanlari var", 'price-daily' in pr and 'price-monthly' in pr and 'price-yearly' in pr)
test("Admin pricing savePricing var", 'savePricing' in pr)
test("Admin pricing Firestore'dan okuma", 'fetch' in pr)

# Admin AI settings
ai_set = open('templates/admin/ai_settings.html').read()
test("Admin AI settings provider ekleme", 'addProvider' in ai_set)
test("Admin AI settings provider silme", 'deleteProvider' in ai_set)
test("Admin AI settings yedek atamasi", 'populateSelects' in ai_set)
test("Admin AI settings yedek uniqueness", 'taken.includes(p.name)' in ai_set or '!taken.includes' in ai_set)

# Admin push
ps = open('templates/admin/push.html').read()
test("Admin push formu var", 'push-form' in ps)
test("Admin push template'leri", 'useTemplate' in ps)

# ═══════════════════════════════════════════════════════
# 7. STATS COUNTER
# ═══════════════════════════════════════════════════════
print("\n📊 7. STATS COUNTER TEST")

stats_src = open('services/stats_counter.py').read()
test("on_user_login metodu", 'on_user_login' in stats_src)
test("on_heartbeat metodu", 'on_heartbeat' in stats_src)
test("get_online_users metodu", 'get_online_users' in stats_src)
test("on_premium_changed metodu", 'on_premium_changed' in stats_src)
test("on_analysis_completed metodu", 'on_analysis_completed' in stats_src)
test("on_credits_changed metodu", 'on_credits_changed' in stats_src)
test("get_overview metodu", 'get_overview' in stats_src)

# ═══════════════════════════════════════════════════════
# 8. ADMOB PLUGIN
# ═══════════════════════════════════════════════════════
print("\n📢 8. ADMOB PLUGIN TEST")

admob_events = open('mobile/node_modules/@capacitor-community/admob/dist/esm/reward/reward-ad-plugin-events.enum.js').read()
test("AdMob Loaded event", 'onRewardedVideoAdLoaded' in admob_events)
test("AdMob FailedToLoad event", 'onRewardedVideoAdFailedToLoad' in admob_events)
test("AdMob Showed event", 'onRewardedVideoAdShowed' in admob_events)
test("AdMob FailedToShow event", 'onRewardedVideoAdFailedToShow' in admob_events)
test("AdMob Dismissed event", 'onRewardedVideoAdDismissed' in admob_events)
test("AdMob Rewarded event", 'onRewardedVideoAdReward' in admob_events)

# Check production AdMob IDs in capacitor config
cap_config = json.load(open('mobile/android/app/src/main/assets/capacitor.config.json'))
ga = cap_config.get('plugins', {}).get('GoogleAuth', {})
test("Capacitor GoogleAuth serverClientId var", bool(ga.get('serverClientId')))
test("Capacitor AdMob testingDevices array", 'testingDevices' in cap_config.get('plugins', {}).get('AdMob', {}))
test("Capacitor PushNotifications presentationOptions var", 'presentationOptions' in cap_config.get('plugins', {}).get('PushNotifications', {}))

# ═══════════════════════════════════════════════════════
# 9. ANDROID MANIFEST
# ═══════════════════════════════════════════════════════
print("\n🤖 9. ANDROID CONFIG TEST")

manifest_xml = open('mobile/android/app/src/main/AndroidManifest.xml').read()
test("INTERNET permission", 'android.permission.INTERNET' in manifest_xml)
test("ACCESS_NETWORK_STATE permission", 'android.permission.ACCESS_NETWORK_STATE' in manifest_xml)
test("AdMob App ID meta-data", 'ca-app-pub-2444093901783574' in manifest_xml)
test("Deep link intent-filter", 'app.orbisastro.online' in manifest_xml)
test("Custom URL scheme", 'com.orbisastro.orbis' in manifest_xml)
test("POST_NOTIFICATIONS permission", 'android.permission.POST_NOTIFICATIONS' in manifest_xml)
test("AD_ID permission", 'com.google.android.gms.permission.AD_ID' in manifest_xml)

strings = open('mobile/android/app/src/main/res/values/strings.xml').read()
test("strings.xml server_client_id var", 'server_client_id' in strings)
test("strings.xml dogru package_name", 'com.orbisastro.orbis' in strings)

gs = json.load(open('mobile/android/app/google-services.json'))
client = [c for c in gs['client'] if 'com.orbisastro.orbis' in str(c)]
test("google-services.json com.orbisastro.orbis var", len(client) > 0)
if client:
    oauths = client[0].get('oauth_client', [])
    has_android = any(c.get('client_type') == 1 for c in oauths)
    test("Android OAuth client (type:1) var", has_android)

proguard = open('mobile/android/app/proguard-rules.pro').read()
test("proguard GoogleAuth korumasi", 'com.codetrixstudio.capacitor.GoogleAuth' in proguard)
test("proguard dogru package name", 'com.orbisastro.orbis' in proguard)
test("proguard Firebase korumasi", 'com.google.firebase' in proguard)

# ═══════════════════════════════════════════════════════
# 10. API ENDPOINT FONKSIYON TEST
# ═══════════════════════════════════════════════════════
print("\n🔌 10. API FONKSIYON TEST")

with app.test_client() as c:
    # Health check
    r = c.get('/api/health')
    test("GET /api/health -> 200", r.status_code == 200)
    if r.status_code == 200:
        data = r.get_json()
        test("  /api/health status healthy", data.get('status') == 'healthy')
    
    # Pricing API
    r = c.get('/api/config/pricing')
    test("GET /api/config/pricing -> 200", r.status_code == 200)
    if r.status_code == 200:
        data = r.get_json()
        test("  /api/config/pricing success", data.get('success'))
        test("  /api/config/pricing data var", 'data' in data)
        if 'data' in data:
            test("  /api/config/pricing daily > 0", data['data'].get('daily', 0) > 0)
    
    # Monetization plans
    r = c.get('/api/monetization/plans')
    test("GET /api/monetization/plans -> 200", r.status_code == 200)
    if r.status_code == 200:
        plans_data = r.get_json()
        test("  /api/monetization/plans 3+ plan var", len(plans_data) >= 3)
    
    # Admin endpoints redirect (no auth)
    for path in ['/admin/api/pricing', '/admin/api/stats/overview', '/admin/api/ai-settings']:
        r = c.get(path)
        test(f"GET {path} -> redirect (302)", r.status_code in [302, 301], f"Got {r.status_code}")
    
    # Root page loads
    r = c.get('/')
    test("GET / -> 200", r.status_code == 200)
    r = c.get('/dashboard')
    test("GET /dashboard -> 200", r.status_code == 200)


# ═══════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"📊 TOPLAM: {total} test")
print(f"   ✅ Geçen: {PASS}")
print(f"   ❌ Kalan: {FAIL}")

if FAIL > 0:
    print(f"\n🔴 HATALAR:")
    for e in ERRORS:
        print(e)
    print(f"\n⚠️ Build almadan once bu hatalari duzeltmelisiniz!")
else:
    print(f"\n🎉 TUM TESTLER GECTI! Build almaya hazirsiniz!")
print("=" * 60)
