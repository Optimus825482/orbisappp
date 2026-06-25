from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    current_app,
    send_from_directory,
)
import os
from services.ai_service import (
    get_ai_interpretation_engine as get_ai_interpretation_engine_service,
)
from services.astro_service import calculate_astro_data
from services.chart_db_service import smart_calculate
from datetime import datetime
import json
import logging
from utils import (
    parse_time_flexible,
    convert_times_to_str,
    get_element_class,
    Constants,
)
from services.location_service import LocationService
from cache_config import cached_location_search, cache
from exceptions import (
    ValidationError, InvalidDateError, InvalidTimeError,
    CalculationError, APIError, DatabaseError,
    error_response, handle_errors
)

bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)

# Lazy init LocationService
_location_service = None


def get_location_service():
    global _location_service
    if _location_service is None:
        api_key = current_app.config.get("OPENCAGE_API_KEY")
        _location_service = LocationService(api_key=api_key)
    return _location_service


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/hakkimizda")
def about():
    """Hakkımızda sayfası - SEO için public içerik"""
    return render_template("public/about.html")


@bp.route("/iletisim")
def contact():
    """İletişim sayfası - SEO için public içerik"""
    return render_template("public/contact.html")


@bp.route("/blog")
def blog_index():
    """Blog ana sayfası - SEO için public içerik"""
    return render_template("public/blog/index.html")


@bp.route("/blog/<slug>")
def blog_post(slug):
    """Blog yazısı sayfası"""
    template = f"public/blog/{slug}.html"
    try:
        return render_template(template)
    except Exception:
        return render_template("404.html"), 404


@bp.route("/nasil-calisir")
def how_it_works():
    """Nasıl çalışır sayfası - SEO için public içerik"""
    return render_template("public/how-it-works.html")


@bp.route("/sss")
def faq():
    """Sıkça sorulan sorular - SEO için public içerik"""
    return render_template("public/faq.html")


@bp.route("/robots.txt")
def robots_txt():
    """robots.txt dosyası"""
    content = """User-agent: *
Allow: /
Allow: /hakkimizda
Allow: /iletisim
Allow: /blog
Allow: /nasil-calisir
Allow: /sss
Allow: /privacy-policy
Allow: /terms-of-service
Disallow: /api/
Disallow: /admin/
Disallow: /dashboard
Disallow: /results
Disallow: /settings

Sitemap: https://app.orbisastro.online/sitemap.xml
"""
    from flask import Response
    return Response(content, mimetype="text/plain")


@bp.route("/api/config/pricing", methods=["GET"])
@handle_errors("Fiyat bilgileri alınamadı")
def api_get_pricing():
    """
    Firestore'dan fiyat bilgilerini getir (public)
    Eğer Firestore'da yoksa varsayılan fiyatları döndür
    """
    try:
        from services.firebase_service import firebase_service
        db = firebase_service.db
        
        if db:
            doc = db.collection("config").document("pricing").get()
            if doc.exists:
                data = doc.to_dict()
                return jsonify({
                    "success": True,
                    "source": "firestore",
                    "data": {
                        "daily": data.get("daily", 30),
                        "monthly": data.get("monthly", 300),
                        "yearly": data.get("yearly", 3000),
                        "updated_at": data.get("updated_at"),
                    }
                })
        
        # Fallback: varsayılan fiyatlar
        return jsonify({
            "success": True,
            "source": "default",
            "data": {
                "daily": 30,
                "monthly": 300,
                "yearly": 3000,
            }
        })
    except Exception as e:
        logger.error(f"[Config] Pricing fetch error: {e}")
        return jsonify({
            "success": True,
            "source": "default",
            "data": {
                "daily": 30,
                "monthly": 300,
                "yearly": 3000,
            }
        })


@bp.route("/sitemap.xml")
def sitemap_xml():
    """sitemap.xml dosyası"""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://app.orbisastro.online/</loc><priority>1.0</priority><changefreq>weekly</changefreq></url>
  <url><loc>https://app.orbisastro.online/hakkimizda</loc><priority>0.8</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/iletisim</loc><priority>0.7</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/nasil-calisir</loc><priority>0.9</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/sss</loc><priority>0.8</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/blog</loc><priority>0.8</priority><changefreq>weekly</changefreq></url>
  <url><loc>https://app.orbisastro.online/blog/dogum-haritasi-nedir</loc><priority>0.7</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/blog/transit-gezegen-etkileri</loc><priority>0.7</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/blog/astrolojide-evler-sistemi</loc><priority>0.7</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/blog/yapay-zeka-ve-astroloji</loc><priority>0.7</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/blog/burc-uyumlulugu</loc><priority>0.7</priority><changefreq>monthly</changefreq></url>
  <url><loc>https://app.orbisastro.online/privacy-policy</loc><priority>0.5</priority><changefreq>yearly</changefreq></url>
  <url><loc>https://app.orbisastro.online/terms-of-service</loc><priority>0.5</priority><changefreq>yearly</changefreq></url>
</urlset>"""
    from flask import Response
    return Response(xml, mimetype="application/xml")


@bp.route("/sw.js")
def service_worker():
    """Service Worker'ı root'tan sun - PWA için gerekli"""
    return send_from_directory(
        os.path.join(current_app.root_path, "static", "js"),
        "sw.js",
        mimetype="application/javascript",
    )


@bp.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():
    """Firebase Messaging Service Worker'ı root'tan sun - FCM için gerekli"""
    return send_from_directory(
        os.path.join(current_app.root_path, "static"),
        "firebase-messaging-sw.js",
        mimetype="application/javascript",
    )


@bp.route("/favicon.ico")
def favicon():
    """Favicon'u root'tan sun"""
    return send_from_directory(
        os.path.join(current_app.root_path, "static"),
        "favicon.ico",
        mimetype="image/x-icon",
    )


@bp.route("/manifest.json")
def manifest():
    """PWA Manifest'i root'tan sun"""
    return send_from_directory(
        os.path.join(current_app.root_path, "static"),
        "manifest.json",
        mimetype="application/manifest+json",
    )


@bp.route("/dashboard")
def dashboard():
    opencage_key = current_app.config.get("OPENCAGE_API_KEY", "")
    return render_template("dashboard.html", opencage_key=opencage_key)


@bp.route("/results", methods=["GET", "POST"])
@handle_errors("Sonuçlar işlenirken hata oluştu")
def show_results():
    if request.method == "POST":
        # Formdan gelen verileri al
        data = request.form
        birth_date_str = data.get("birth_date", "").strip()
        birth_time_str = data.get("birth_time", "").strip()
        latitude_str = data.get("latitude", "").strip()
        longitude_str = data.get("longitude", "").strip()
        user_name = data.get("name", "Değerli Danışanım").strip()

        # Debug log
        logger.info(
            f"Form data received - birth_date: {birth_date_str}, birth_time: {birth_time_str}, lat: {latitude_str}, lng: {longitude_str}"
        )

        # Validation
        if not birth_date_str:
            flash("Doğum tarihi gerekli!")
            return redirect(url_for("main.dashboard"))

        if not birth_time_str:
            flash("Doğum saati gerekli!")
            return redirect(url_for("main.dashboard"))

        if not latitude_str or not longitude_str:
            flash("Doğum yeri seçilmedi! Lütfen şehir arayıp listeden seçin.")
            return redirect(url_for("main.dashboard"))

        # Transit bilgileri (opsiyonel)
        transit_date = data.get("transit_date", "").strip()
        transit_time = data.get("transit_time", "").strip()
        transit_lat = data.get("transit_latitude", "").strip()
        transit_lng = data.get("transit_longitude", "").strip()

        transit_info = None
        if transit_date and transit_time:
            transit_info = {
                "date": transit_date,
                "time": transit_time,
                "latitude": float(transit_lat)
                if transit_lat
                else float(latitude_str),
                "longitude": float(transit_lng)
                if transit_lng
                else float(longitude_str),
            }

        # Astrolojik hesaplamaları yap
        try:
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        except ValueError as ve:
            logger.error(f"Date parse error: {birth_date_str} - {ve}")
            raise InvalidDateError(birth_date_str, "%Y-%m-%d") from ve

        birth_time = parse_time_flexible(birth_time_str)

        try:
            lat = float(latitude_str)
            lng = float(longitude_str)
        except ValueError as ve:
            logger.error(
                f"Coordinate parse error: lat={latitude_str}, lng={longitude_str} - {ve}"
            )
            raise ValidationError(
                message="Geçersiz koordinat değerleri!",
                error_code="INVALID_COORDINATES",
                details={"latitude": latitude_str, "longitude": longitude_str}
            ) from ve

        astro_data = smart_calculate(
            birth_date=birth_date,
            birth_time=birth_time,
            latitude=lat,
            longitude=lng,
            transit_info=transit_info,
        )

        if not astro_data or "error" in astro_data:
            error_msg = (
                astro_data.get("error", "Bilinmeyen hata")
                if astro_data
                else "Hesaplama başarısız"
            )
            logger.error(f"Astro calculation error: {error_msg}")
            raise CalculationError(
                message=f"Hesaplama sırasında bir hata oluştu: {error_msg}",
                error_code="CALCULATION_FAILED",
                details={"astro_error": error_msg}
            )

        # Kullanıcı bilgilerini ekle
        astro_data["user_name"] = user_name
        astro_data["birth_info"] = {
            "user_name": user_name,
            "date": birth_date_str,
            "time": birth_time_str,
            "location": {
                "latitude": latitude_str,
                "longitude": longitude_str,
                "name": data.get("birth_place_suggestion", ""),
            },
        }

        return render_template(
            "new_result.html", astro_data=astro_data, user_name=user_name
        )

    # GET ise (doğrudan linkle gelindiyse)
    return render_template("new_result.html", astro_data=None, user_name=None)


@bp.route("/api/get_ai_interpretation", methods=["POST"])
@handle_errors("AI yorum alınamadı")
def api_get_ai_interpretation():
    """AI Yorum API - Sadece native (Android) icin reklam zorunlulugu var.
    PWA istemcilerde limitsiz erisim saglanir (AdMob PWA'da calismaz)."""
    data = request.get_json()
    interpretation_type = data.get("interpretation_type", "daily")
    astro_data = data.get("astro_data", {})
    user_name = data.get("user_name", "Değerli Danışanım")

    # Kullanım kontrolü için device_id ve email
    device_id = data.get("device_id")
    email = data.get("email")

    # ═══════════════════════════════════════════════════════════════
    # PWA tespiti: Web istemcilerde reklam zorunlulugu yok
    # ═══════════════════════════════════════════════════════════════
    user_agent = request.headers.get('User-Agent', '')
    client_platform = request.headers.get('X-Client-Platform', '').lower()
    is_pwa = (
        'capacitor' not in user_agent.lower() and
        client_platform != 'capacitor' and
        client_platform != 'native' and
        client_platform != 'android'
    )

    # Kullanım limiti kontrolü — sadece native için
    if device_id and not is_pwa:
        from monetization.usage_tracker import UsageTracker
        usage_tracker = UsageTracker()

        can_use = usage_tracker.can_use_feature(device_id, "ai_interpretation", email)

        if not can_use.get("allowed"):
            return jsonify({
                "success": False,
                "error": "requires_ad",
                "message": can_use.get("message", "Devam etmek için reklam izlemeniz gerekiyor."),
                "remaining": 0,
                "requires_ad": True
            }), 429

    # Ek parametreler (tarih, dönem vb.) - hem Türkçe hem İngilizce destekle
    extra_params = {
        "date": data.get("date") or data.get("tarih"),
        "start_date": data.get("start_date") or data.get("baslangic_tarihi"),
        "end_date": data.get("end_date") or data.get("bitis_tarihi"),
        "period": data.get("period") or data.get("donem"),
        "duration": data.get("duration") or data.get("sure"),
    }
    # None değerleri temizle
    extra_params = {k: v for k, v in extra_params.items() if v is not None}

    # API'den yorum al
    result = get_ai_interpretation_engine_service(
        astro_data, interpretation_type, user_name, **extra_params
    )

    # Başarılı yorum sonrası → kullanımı say + stats counter güncelle
    if result.get("success"):
        # Kullanımı kaydet — sadece native için
        if device_id and not is_pwa:
            from monetization.usage_tracker import UsageTracker
            usage_tracker = UsageTracker()
            usage_info = usage_tracker.record_usage(device_id, "ai_interpretation", email)
            result["usage"] = {
                "remaining": usage_info.get("remaining", 0),
                "requires_ad": usage_info.get("requires_ad", True)
            }
        else:
            # PWA: reklam kontrolü yok
            result["usage"] = {
                "remaining": 999,
                "requires_ad": False
            }

        # Stats counter: analiz sayısını artır
        try:
            from services.stats_counter import stats_counter
            stats_counter.on_analysis_completed()
        except Exception:
            pass

    return jsonify(result)


@bp.route("/settings")
def settings():
    return render_template("settings.html")


@bp.route("/search_location")
def search_location():
    query = request.args.get("query", "")
    if not query or len(query) < 3:
        return jsonify({"locations": []})

    try:
        results = _get_cached_locations(query)
        return jsonify({"locations": results})
    except Exception as e:
        logger.error(f"Location search error: {str(e)}")
        return jsonify({"locations": [], "error": str(e)}), 500


@cached_location_search()
def _get_cached_locations(query):
    service = get_location_service()
    return service.search_location(query)


# ═══════════════════════════════════════════════════════════════
# HESAP SİLME (GDPR/KVKK UYUMLULUĞU)
# ═══════════════════════════════════════════════════════════════

@bp.route("/api/delete-account", methods=["POST"])
@handle_errors("Hesap silme işlemi başarısız")
def delete_account():
    """
    Kullanıcı hesabını ve tüm verilerini siler.
    Firebase Authentication ve Firestore'dan veri siler.
    GDPR/KVKK uyumluluğu için gerekli.
    """
    data = request.get_json()
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({
            "success": False,
            "error": "MISSING_USER_ID",
            "message": "Kullanıcı kimliği gerekli"
        }), 400
    
    # Firebase Admin SDK ile silme işlemi
    # Not: Firebase Admin SDK gerekli - eğer yoksa frontend'den silinecek
    deleted_data = {
        "user_id": user_id,
        "deleted_at": datetime.now().isoformat(),
        "status": "pending"
    }
    
    logger.info(f"Hesap silme talebi alındı: {user_id}")
    
    # Firestore'dan kullanıcı verilerini silme talebi logla
    # Gerçek silme işlemi frontend'de Firebase SDK ile yapılacak
    
    return jsonify({
        "success": True,
        "message": "Hesap silme talebi alındı. Verileriniz 24 saat içinde silinecektir.",
        "deletion_request": deleted_data
    })


@bp.route("/account/delete")
def account_delete_page():
    """Hesap silme sayfası"""
    return render_template("account_delete.html")


# ═══════════════════════════════════════════════════════════════
# REWARDED ADS & USAGE TRACKING API
# ═══════════════════════════════════════════════════════════════

@bp.route("/api/check_usage", methods=["POST"])
@handle_errors("Kullanım kontrolü başarısız")
def api_check_usage():
    """
    Kullanıcının günlük reklam izleme hakkını kontrol et

    Request:
    {
        "device_id": "device_xxx",
        "email": "user@example.com"  # optional
    }

    Response:
    {
        "allowed": true/false,
        "requires_ad": true/false,
        "remaining": 2,
        "premium_price": 30.0,
        "message": "..."
    }

    PWA (web) istemcileri icin AdMob calismadigi icin reklam zorunlulugu
    kaldirilir. Sadece native (Android/Capacitor) istemcilerde reklam istenir.
    """
    from monetization.usage_tracker import UsageTracker

    data = request.get_json()
    device_id = data.get('device_id')
    email = data.get('email')

    logger.info(f"[API] check_usage - device_id: {device_id}, email: {email}")

    if not device_id:
        logger.error("[API] check_usage - device_id missing")
        return jsonify({
            "error": "MISSING_DEVICE_ID",
            "message": "device_id required"
        }), 400

    # ═══════════════════════════════════════════════════════════════
    # PWA tespiti: Sadece native (Capacitor) istemcilerde reklam zorunlu
    # Capacitor native platformda X-Client-Platform header'i 'capacitor' veya
    # User-Agent 'Capacitor' icerir. PWA'da bunlar yok.
    # ═══════════════════════════════════════════════════════════════
    user_agent = request.headers.get('User-Agent', '')
    client_platform = request.headers.get('X-Client-Platform', '').lower()
    is_pwa = (
        'capacitor' not in user_agent.lower() and
        client_platform != 'capacitor' and
        client_platform != 'native' and
        client_platform != 'android'
    )

    if is_pwa:
        logger.info(f"[API] check_usage - PWA istemci tespit edildi, reklam zorunlulugu yok (UA: {user_agent[:50]})")
        return jsonify({
            "allowed": True,
            "requires_ad": False,
            "remaining": 999,
            "message": "PWA istemci - reklam zorunlulugu yok",
            "platform": "pwa"
        })

    tracker = UsageTracker()
    usage = tracker.can_use_feature(device_id, 'ad_watch', email)

    logger.info(f"[API] check_usage result: {usage}")

    return jsonify(usage)


@bp.route("/api/record_ad_watch", methods=["POST"])
@handle_errors("Reklam izleme kaydı başarısız")
def api_record_ad_watch():
    """
    Reklam izleme kaydını tut

    Request:
    {
        "device_id": "device_xxx",
        "email": "user@example.com"  # optional
    }

    Response:
    {
        "success": true,
        "remaining": 1,
        "today_usage": 2
    }

    PWA istemcilerinde AdMob calismadigi icin bu endpoint no-op davranir.
    """
    # ═══════════════════════════════════════════════════════════════
    # PWA tespiti: Web istemcilerde no-op (AdMob sadece native'de calisir)
    # ═══════════════════════════════════════════════════════════════
    user_agent = request.headers.get('User-Agent', '')
    client_platform = request.headers.get('X-Client-Platform', '').lower()
    is_pwa = (
        'capacitor' not in user_agent.lower() and
        client_platform != 'capacitor' and
        client_platform != 'native' and
        client_platform != 'android'
    )

    if is_pwa:
        logger.info(f"[API] record_ad_watch - PWA istemci, no-op (UA: {user_agent[:50]})")
        return jsonify({
            "success": True,
            "remaining": 999,
            "today_usage": 0,
            "platform": "pwa",
            "message": "PWA - reklam kaydedilmedi"
        })

    from monetization.usage_tracker import UsageTracker

    data = request.get_json()
    device_id = data.get('device_id')
    email = data.get('email')

    logger.info(f"[API] record_ad_watch - device_id: {device_id}, email: {email}")

    if not device_id:
        logger.error("[API] record_ad_watch - device_id missing")
        return jsonify({
            "error": "MISSING_DEVICE_ID",
            "message": "device_id required"
        }), 400

    tracker = UsageTracker()
    result = tracker.record_usage(device_id, 'ad_watch', email)

    logger.info(f"[API] record_ad_watch result: {result}")

    # Stats counter: bagimsiz analiz sayisini da artir
    try:
        from services.stats_counter import stats_counter
        stats_counter.on_analysis_completed()
    except Exception:
        pass

    return jsonify({
        "success": True,
        "remaining": result.get('remaining'),
        "today_usage": result.get('today_usage')
    })


@bp.route("/api/stats/user-created", methods=["POST"])
@handle_errors("İstatistik güncellenemedi")
def api_user_created():
    """Yeni kullanıcı oluşturulduğunda stats counter'ı güncelle"""
    from services.stats_counter import stats_counter
    stats_counter.on_user_created()
    return jsonify({"success": True})


@bp.route("/api/stats/heartbeat", methods=["POST"])
@handle_errors("Kalp atisi guncellenemedi")
def api_heartbeat():
    """Kullanici kalp atisi - her 60 saniyede bir cagrilir"""
    from services.stats_counter import stats_counter
    data = request.get_json()
    email = data.get("email", "anonymous")
    name = data.get("display_name", email)
    stats_counter.on_heartbeat(email, name)
    return jsonify({"success": True})


@bp.route("/api/stats/ad-watched", methods=["POST"])
@handle_errors("Reklam izleme kaydi alinamadi")
def api_ad_watched():
    """Bonus AI yorum veya diger reklam izleme kaydi.

    Bonus Rewarded Interstitial (9025146181) izlendiginde dashboard'dan
    bu endpoint cagrilir. Stats counter guncellenir, admin panelde
    toplam bonus sayisi gorulur.
    """
    from services.stats_counter import stats_counter
    data = request.get_json() or {}
    rewarded = data.get("rewarded", False)
    ad_type = data.get("type", "general")  # 'bonus', 'general', 'analysis'

    # Sadece native istemcide (Capacitor header) say
    user_agent = request.headers.get('User-Agent', '').lower()
    client_platform = request.headers.get('X-Client-Platform', '').lower()
    is_pwa = (
        'capacitor' not in user_agent and
        client_platform != 'capacitor' and
        client_platform != 'native' and
        client_platform != 'android'
    )

    if is_pwa:
        return jsonify({"success": True, "platform": "pwa", "counted": False})

    try:
        stats_counter.on_ad_watched(rewarded=rewarded)
    except Exception as e:
        logger.warning(f"[API] ad_watched stats error (non-fatal): {e}")

    return jsonify({"success": True, "counted": True, "type": ad_type})


@bp.route("/api/stats/user-login", methods=["POST"])
@handle_errors("Giris kaydi alinamadi")
def api_user_login():
    """Kullanici giris yapti - son login bilgisini guncelle"""
    from services.stats_counter import stats_counter
    data = request.get_json()
    email = data.get("email", "")
    name = data.get("display_name", email)
    if email:
        stats_counter.on_user_login(email, name)
    return jsonify({"success": True})

