"""
Monetization API Routes - SADECE NATIVE (ANDROID) İÇİN
Premium/abonelik sistemi tamamen kaldırıldı.
Sadece native (Capacitor) istemcilerde reklam takibi yapılır.
PWA (web) istemcilerde bu endpoint'ler no-op döner — sınırsız erişim.
"""
import logging
from flask import Blueprint, request, jsonify
from monetization.usage_tracker import UsageTracker

logger = logging.getLogger(__name__)

monetization_bp = Blueprint("monetization", __name__, url_prefix="/api/monetization")

usage_tracker = UsageTracker()


def _is_pwa_request() -> bool:
    """PWA (web) istemci mi tespit et. Capacitor header'ı yoksa PWA."""
    user_agent = request.headers.get('User-Agent', '').lower()
    client_platform = request.headers.get('X-Client-Platform', '').lower()
    is_pwa = (
        'capacitor' not in user_agent and
        client_platform != 'capacitor' and
        client_platform != 'native' and
        client_platform != 'android'
    )
    return is_pwa


@monetization_bp.route("/check-usage", methods=["POST"])
def check_usage():
    """Kullanıcının kullanım durumunu kontrol et.

    PWA (web) istemcilerde AdMob çalışmadığı için sınırsız erişim döner.
    """
    if _is_pwa_request():
        logger.info(f"[monetization] check-usage - PWA istemci, no-op (UA: {request.headers.get('User-Agent', '')[:50]})")
        return jsonify({
            "usage": {
                "is_premium": False,
                "is_admin": False,
                "remaining": 999,
                "requires_ad": False,
                "show_ads": False,
            },
            "can_use": {"allowed": True, "requires_ad": False, "remaining": 999},
            "show_ads": False,
            "platform": "pwa",
            "message": "PWA istemci - reklam zorunluluğu yok"
        })

    data = request.get_json()
    device_id = data.get("device_id")

    if not device_id:
        return jsonify({"error": "device_id gerekli"}), 400

    usage = usage_tracker.get_user_usage(device_id)
    can_use = usage_tracker.can_use_feature(device_id)

    return jsonify({
        "usage": usage,
        "can_use": can_use,
        "show_ads": True
    })


@monetization_bp.route("/record-usage", methods=["POST"])
def record_usage():
    """Kullanımı kaydet (reklam izlendi).

    PWA (web) istemcilerde no-op — AdMob sadece native'de çalışır.
    """
    if _is_pwa_request():
        logger.info(f"[monetization] record-usage - PWA istemci, no-op")
        return jsonify({
            "success": True,
            "remaining": 999,
            "today_usage": 0,
            "platform": "pwa",
            "message": "PWA - reklam kaydedilmedi"
        })

    data = request.get_json()
    device_id = data.get("device_id")
    feature = data.get("feature", "interpretation")

    if not device_id:
        return jsonify({"error": "device_id gerekli"}), 400

    result = usage_tracker.record_usage(device_id, feature)
    return jsonify(result)
