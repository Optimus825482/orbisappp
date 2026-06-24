import os
import sys
import logging

# GCP Regional Access Boundary kontrolünü firebase_admin import'undan
# ÖNCE devre dışı bırak. Bu, ana giriş noktasında set edilmesi gereken
# erken bir ortam değişkenidir — runtime'da set etmek client init'i
# için GEÇ kalır (Precondition check zaten çalışmış olur).
os.environ.setdefault('FIRESTORE_ACCESS_BOUNDARY_DISABLED', 'true')
os.environ.setdefault('GOOGLE_CLOUD_FIRESTORE_ACCESS_BOUNDARY_DISABLED', 'true')

from flask import Flask, send_from_directory, jsonify
import config
from extensions import cors, init_extensions
from flask_talisman import Talisman


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    # Config yükle
    app_config = config.get_config()
    app.config.from_object(app_config)

    if test_config is not None:
        app.config.from_mapping(test_config)

    # Blueprintleri kaydet
    from routes import bp, legal_bp

    app.register_blueprint(bp)
    app.register_blueprint(legal_bp)

    # Push Notification routes
    try:
        from routes.push_routes import push_bp

        app.register_blueprint(push_bp)
    except ImportError as e:
        logging.warning(f"Push routes yüklenemedi: {e}")

    # Admin Dashboard routes
    try:
        from routes.admin import admin_bp

        app.register_blueprint(admin_bp)
    except ImportError as e:
        logging.warning(f"Admin routes yüklenemedi: {e}")

    # Monetization routes
    try:
        from monetization.routes import monetization_bp

        app.register_blueprint(monetization_bp)
    except ImportError as e:
        logging.warning(f"Monetization routes yüklenemedi: {e}")

    # Android App Links - assetlinks.json
    @app.route("/.well-known/assetlinks.json")
    def assetlinks():
        return send_from_directory(
            os.path.join(app.static_folder, ".well-known"),
            "assetlinks.json",
            mimetype="application/json",
        )

    # app-ads.txt / ads.txt - AdMob reklam doğrulama (504 fix)
    # send_file() send_from_directory()'den daha hızlı çünkü ekstra os.path.isfile() lookup yapmaz
    @app.route("/app-ads.txt")
    def app_ads_txt():
        from flask import send_file
        return send_file(
            os.path.join(app.static_folder, "app-ads.txt"),
            mimetype="text/plain",
            max_age=3600,
        )

    @app.route("/ads.txt")
    def ads_txt():
        from flask import send_file
        return send_file(
            os.path.join(app.static_folder, "ads.txt"),
            mimetype="text/plain",
            max_age=3600,
        )

    # Filtreleri ekle
    import utils

    app.jinja_env.filters["date"] = utils.format_date
    app.jinja_env.filters["time"] = utils.format_time
    app.jinja_env.filters["safe_round"] = utils.safe_round

    # Health Check Endpoint (Docker/Coolify için)
    @app.route("/api/health")
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "orbis-backend",
            "version": "1.0.0"
        }), 200

    # Extension'ları başlat
    init_extensions(app)

    # Security headers and HTTPS enforcement
    # CSP mobil uygulama için devre dışı - inline script/style ve CDN'ler gerekli
    Talisman(
        app,
        force_https=os.getenv("FLASK_ENV") == "production",
        strict_transport_security=os.getenv("FLASK_ENV") == "production",
        session_cookie_secure=os.getenv("FLASK_ENV") == "production",
        content_security_policy=None,  # CSP devre dışı - mobil app uyumluluğu için
    )

    # COOP/COEP — Flask-Talisman 1.1.0 bu parametreleri desteklemiyor, manuel ekleme
    # Firebase Google signInWithPopup için COOP same-origin popup blokluyor
    # "same-origin-allow-popups" popup pencerelerine izin verir
    @app.after_request
    def set_cross_origin_headers(response):
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
        return response
    
    # CSRF protection için secret key kontrolü
    if not app.config.get("SECRET_KEY"):
        app.logger.warning("SECRET_KEY not set! Using temporary key.")
        app.config["SECRET_KEY"] = os.urandom(32)

    # Tailwind CSS varlık kontrolü (bir kez yapalım)
    tailwind_path = (
        os.path.join(app.static_folder, "css/tailwind.css")
        if app.static_folder
        else None
    )
    tailwind_exists = os.path.exists(tailwind_path) if tailwind_path else False

    @app.context_processor
    def inject_tailwind_css():
        return dict(tailwind_exists=tailwind_exists)

    return app
