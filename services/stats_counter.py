"""
ORBIS Stats Counter Service
- Firestore stats/dashboard dokumanini yonetir
- Her kullanici isleminde counter'lari gunceller
- Admin dashboard sayfalama icin optimize edilmistir
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Field yollari
FIELD_TOTAL_USERS = "total_users"
FIELD_PREMIUM_USERS = "premium_users"
FIELD_FREE_USERS = "free_users"
FIELD_TOTAL_CREDITS = "total_credits"
FIELD_TOTAL_ANALYSES = "total_analyses"
FIELD_ACTIVE_TODAY = "active_today"


class StatsCounter:
    """Firestore counter yonetimi - her islemde sadece ilgili field'i gunceller"""

    def __init__(self):
        self.db = None
        self._init_db()

    def _init_db(self):
        try:
            from services.firebase_service import firebase_service
            self.db = firebase_service.db
        except Exception as e:
            logger.error(f"[Stats] DB init error: {e}")

    @property
    def _doc(self):
        """stats/dashboard dokuman referansi"""
        if not self.db:
            return None
        return self.db.collection("stats").document("dashboard")

    def _increment(self, field: str, amount: int = 1):
        """Bir counter field'ini Increment ile guncelle"""
        if not self.db:
            return
        try:
            from firebase_admin import firestore
            self._doc.update({field: firestore.Increment(amount)})
        except Exception as e:
            logger.error(f"[Stats] Increment error ({field}): {e}")

    def _set_active_today(self, count: int):
        """active_today degerini dogrudan set et (gu sonu sifirlanir)"""
        if not self.db:
            return
        try:
            self._doc.update({FIELD_ACTIVE_TODAY: count})
        except Exception as e:
            logger.error(f"[Stats] set_active_today error: {e}")

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API - Kullanici islemleri
    # ═══════════════════════════════════════════════════════════════

    def on_user_created(self, is_premium: bool = False):
        """Yeni kullanici olustu"""
        self._increment(FIELD_TOTAL_USERS, 1)
        if is_premium:
            self._increment(FIELD_PREMIUM_USERS, 1)
        else:
            self._increment(FIELD_FREE_USERS, 1)

    def on_user_deleted(self, was_premium: bool = False, credits: int = 0, analyses: int = 0):
        """Kullanici silindi"""
        self._increment(FIELD_TOTAL_USERS, -1)
        if was_premium:
            self._increment(FIELD_PREMIUM_USERS, -1)
        else:
            self._increment(FIELD_FREE_USERS, -1)
        if credits:
            self._increment(FIELD_TOTAL_CREDITS, -credits)
        if analyses:
            self._increment(FIELD_TOTAL_ANALYSES, -analyses)

    def on_premium_changed(self, became_premium: bool):
        """Premium durumu degisti"""
        if became_premium:
            self._increment(FIELD_PREMIUM_USERS, 1)
            self._increment(FIELD_FREE_USERS, -1)
        else:
            self._increment(FIELD_PREMIUM_USERS, -1)
            self._increment(FIELD_FREE_USERS, 1)

    def on_credits_changed(self, delta: int):
        """Kredi degisti (+/-)"""
        if delta != 0:
            self._increment(FIELD_TOTAL_CREDITS, delta)

    def on_analysis_completed(self):
        """Analiz yapildi"""
        self._increment(FIELD_TOTAL_ANALYSES, 1)

    def on_daily_activity(self, today: str):
        """Gunluk aktif kullanici sayisini guncelle"""
        if not self.db:
            return
        try:
            # Bugunku aktif kullanicilari say (select projection ile)
            result = self.db.collection("users").where(
                filter=("dailyUsage.date", "==", today)
            ).count().get()
            count = result[0][0].value
            self._set_active_today(count)
        except Exception as e:
            logger.error(f"[Stats] daily_activity error: {e}")

    def on_user_login(self, email: str, display_name: str):
        """Kullanici giris yapti - son login kaydi"""
        if not self.db:
            return
        try:
            now = datetime.now()
            self._doc.update({
                "last_login_email": email,
                "last_login_name": display_name or email,
                "last_login_time": now.isoformat(),
            })
        except Exception as e:
            logger.error(f"[Stats] login tracking error: {e}")

    def on_heartbeat(self, email: str, display_name: str):
        """Aktif kullanici kalp atisi - heartbeat dokumanina yaz"""
        if not self.db:
            return
        try:
            from firebase_admin import firestore
            from datetime import datetime, timezone
            # ⚠️ SERVER_TIMESTAMP kullanma - filtrelemede sorun cikarir
            # Gercek timestamp ile yaz, boylece sorgu calisir
            now = datetime.now(timezone.utc).isoformat()
            key = email.replace("@", "_at_").replace(".", "_dot_")
            self.db.collection("stats_heartbeats").document(key).set({
                "email": email,
                "display_name": display_name or email,
                "last_seen": now,
            })
        except Exception as e:
            logger.error(f"[Stats] heartbeat error: {e}")

    def get_online_users(self, within_minutes: int = 5) -> list:
        """Son N dakikada heartbeat atan kullanicilar"""
        if not self.db:
            return []
        try:
            from datetime import datetime, timedelta, timezone
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=within_minutes)).isoformat()
            docs = list(self.db.collection("stats_heartbeats")
                        .where("last_seen", ">=", cutoff)
                        .stream())
            users = []
            for d in docs:
                data = d.to_dict()
                users.append({
                    "email": data.get("email"),
                    "display_name": data.get("display_name"),
                    "last_seen": data.get("last_seen", ""),
                })
            return users
        except Exception as e:
            logger.error(f"[Stats] online error: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════
    # ADMIN DASHBOARD - Hizli okuma (tek dokuman, 1 read)
    # ═══════════════════════════════════════════════════════════════

    def get_overview(self) -> Optional[dict]:
        """Dashboard icin tum istatistikleri tek dokumandan oku (SADECE 1 READ)"""
        if not self.db:
            return None

        # ONCE counter dokumanindan oku
        try:
            doc = self._doc.get()
            if doc.exists:
                data = doc.to_dict()
                # Gunluk aktif sayisini guncelle (arka planda)
                self.on_daily_activity(datetime.now().strftime("%Y-%m-%d"))
                return data
        except Exception as e:
            logger.error(f"[Stats] Overview read error: {e}")

        # COUNTER YOKSA fallback: `select()` projection ile sadece gerekli field'lar
        try:
            logger.info("[Stats] Counter dokumani bulunamadi, fallback select() ile okunuyor...")
            docs = list(self.db.collection("users").select([
                "isPremium", "credits", "totalAnalyses", "dailyUsage.date"
            ]).stream())

            total = len(docs)
            premium = 0
            credits = 0
            analyses = 0
            today = datetime.now().strftime("%Y-%m-%d")
            active = 0

            for d in docs:
                data = d.to_dict()
                if data.get("isPremium"):
                    premium += 1
                credits += data.get("credits", 0) or 0
                analyses += data.get("totalAnalyses", 0) or 0
                if data.get("dailyUsage", {}).get("date") == today:
                    active += 1

            return {
                "total_users": total,
                "premium_users": premium,
                "free_users": total - premium,
                "total_credits": credits,
                "total_analyses": analyses,
                "active_today": active,
            }
        except Exception as e:
            logger.error(f"[Stats] Fallback read error: {e}")
            return None


stats_counter = StatsCounter()
