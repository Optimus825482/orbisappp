/**
 * ORBIS Monetizasyon & Capacitor Bridge
 * - Sadece reklam destekli uygulama
 * - PREMIUM KALDIRILDI: Uygulama tamamen ucretsiz.
 *   Geriye uyumluluk icin state.isPremium her zaman false dondurulur,
 *   premium satin alma/paket gosterim fonksiyonlari no-op.
 *
 * KURALLAR:
 * - Her analiz icin Rewarded reklam ZORUNLU
 * - Banner + interstitial ek gelir
 * - Premium satin alma KAPALI
 */

const OrbisBridge = {
  // ═══════════════════════════════════════════════════════════════
  // YAPILANDIRMA
  // ═══════════════════════════════════════════════════════════════

  CONFIG: {
    // Ücretsiz kullanıcı limitleri
    // ARTIK HER ANALİZ İÇİN REKLAM ZORUNLU (Premium hariç)
    FREE_FIRST_DAY_TOTAL: 999, // Sınırsız (reklam izleyerek)
    FREE_FIRST_DAY_NO_AD: 0, // Reklamsız hak YOK
    FREE_DAILY_LIMIT: 999, // Sınırsız (reklam izleyerek)

    // Premium paketleri
    PREMIUM_PACKAGES: [
      { id: "daily", name: "Günlük", price: 30, credits: 0, months: 0 },
      { id: "monthly", name: "Aylık", price: 300, credits: 0, months: 1 },
      { id: "yearly", name: "Yıllık", price: 3000, credits: 0, months: 12 },
    ],

    // AdMob ID'leri — tek kaynak window.ADMOB_CONFIG (static/js/admob-config.js).
    // IS_TEST flag tek yerde; test/prod blokları kaldırıldı.
    ADMOB_CONFIG_REF: true, // window.ADMOB_CONFIG'ten beslenir
    ADMOB_FALLBACK: {
      // window.ADMOB_CONFIG yüklenmezse (script tag eksikse) fallback
      APP_ID: "ca-app-pub-2444093901783574~9279937953",
      BANNER: "ca-app-pub-2444093901783574/1791137239",
      INTERSTITIAL: "ca-app-pub-2444093901783574/8681172156",
      REWARDED: "ca-app-pub-2444093901783574/9994253824",
      REWARDED_ANALIZ: "ca-app-pub-2444093901783574/3701964485",
    },

    // Interstitial gösterim aralığı (her X analizde bir)
    INTERSTITIAL_INTERVAL: 3,

    // Test modu - Production için false
    IS_TESTING: false,
  },

  /** AdMob config döndür — tek kaynak window.ADMOB_CONFIG; fallback CONFIG.ADMOB_FALLBACK. */
  _getAdmob() {
    const cfg = window.ADMOB_CONFIG;
    if (cfg) {
      return {
        APP_ID: cfg.appId,
        BANNER: cfg.bannerId,
        INTERSTITIAL: cfg.interstitialId,
        REWARDED: cfg.rewardedInterstitialId,
        REWARDED_ANALIZ: cfg.rewardedAnalysisId,
      };
    }
    return this.CONFIG.ADMOB_FALLBACK;
  },

  // ═══════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════

  state: {
    isNative: false,
    // Premium kaldirildi: her zaman false. Eski localStorage verileri temizlenir.
    isPremium: false,
    credits: 0,
    premiumPackageId: null, // Hangi premium paketi aldı (artik kullanilmiyor)

    // Ücretsiz kullanıcı için
    installDate: null, // İlk kurulum tarihi
    todayUsage: 0, // Bugünkü kullanım
    todayAdsWatched: 0, // Bugün izlenen reklam
    lastUsageDate: null, // Son kullanım tarihi
    totalAnalyses: 0, // Toplam analiz (interstitial için)

    // Premium için (artik kullanilmiyor)
    premiumExpiry: null, // Premium bitiş tarihi
  },

  // ═══════════════════════════════════════════════════════════════
  // FIRESTORE'DAN FİYAT YÜKLEME
  // ═══════════════════════════════════════════════════════════════

  async loadPricingFromServer() {
    try {
      const res = await fetch("/api/config/pricing");
      const json = await res.json();

      if (json.success && json.data) {
        const p = json.data;
        console.log("[ORBIS] Fiyatlar Firestore'dan yüklendi:", p);

        // PREMIUM_PACKAGES fiyatlarını güncelle
        const dailyPkg = this.CONFIG.PREMIUM_PACKAGES.find(x => x.id === "daily");
        const monthlyPkg = this.CONFIG.PREMIUM_PACKAGES.find(x => x.id === "monthly");
        const yearlyPkg = this.CONFIG.PREMIUM_PACKAGES.find(x => x.id === "yearly");

        if (dailyPkg) dailyPkg.price = p.daily || dailyPkg.price;
        if (monthlyPkg) monthlyPkg.price = p.monthly || monthlyPkg.price;
        if (yearlyPkg) yearlyPkg.price = p.yearly || yearlyPkg.price;

        this.CONFIG.PRICING_SOURCE = "firestore";
      }
    } catch (e) {
      console.log("[ORBIS] Fiyatlar sunucudan yüklenemedi, varsayılanlar kullanılacak:", e.message);
      this.CONFIG.PRICING_SOURCE = "default";
    }

    // UI'ı güncelle (fiyatlar değişmiş olabilir)
    this.updateUI();
  },

  // ═══════════════════════════════════════════════════════════════
  // PREMIUM DOĞRULAMA - localStorage'daki premium'u backend'den kontrol et
  // ═══════════════════════════════════════════════════════════════

  async verifyPremiumWithBackend() {
    // DEPRECATED: Premium kaldirildi. Eski premium state'lerini temizle.
    if (this.state.isPremium || this.state.premiumPackageId || this.state.premiumExpiry || this.state.credits > 0) {
      console.info("[ORBIS] Eski premium/credit state temizleniyor (premium kaldirildi).");
      this.state.isPremium = false;
      this.state.premiumPackageId = null;
      this.state.premiumExpiry = null;
      this.state.credits = 0;
      this.saveState();
    }
  },

  getDeviceId() {
    let id = localStorage.getItem("orbis_device_id");
    if (!id) {
      id = "dev_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
      localStorage.setItem("orbis_device_id", id);
    }
    return id;
  },

  // ═══════════════════════════════════════════════════════════════
  // BAŞLATMA
  // ═══════════════════════════════════════════════════════════════

  async init() {
    console.log("[ORBIS] Monetizasyon sistemi başlatılıyor...");

    // State'i yükle
    this.loadState();

    // Günlük reset kontrolü
    this.checkDailyReset();

    // ═══════════════════════════════════════════════════════════════
    // FIRESTORE'DAN FİYATLARI ÇEK
    // ═══════════════════════════════════════════════════════════════
    this.loadPricingFromServer();

    // ⚠️ KRİTİK: Premium doğrulama - localStorage'da premium varsa
    // backend'den kontrol et ve state'i düzelt. Bekle ki analiz
    // başlamadan premium durumu netleşsin.
    await this.verifyPremiumWithBackend();

    // ═══════════════════════════════════════════════════════════════
    // PLATFORM TESPİTİ (iyileştirilmiş)
    // ═══════════════════════════════════════════════════════════════
    
    // 1. Capacitor Native API kontrolü
    if (typeof Capacitor !== "undefined" && Capacitor.isNativePlatform()) {
      this.state.isNative = true;
      console.log("[ORBIS] Native platform tespit edildi (Capacitor API)");
    }
    // 2. UA kontrolü - Android/iOS
    else if (/android|ipad|iphone|ipod/i.test(navigator.userAgent)) {
      this.state.isNative = true;
      console.log("[ORBIS] Native platform tespit edildi (User-Agent)");
    }
    // 3. Dosya protokolü kontrolü (Capacitor WebView file:// ile çalışır)
    else if (location.protocol === 'file:' || location.protocol === 'capacitor:') {
      this.state.isNative = true;
      console.log("[ORBIS] Native platform tespit edildi (protocol)");
    }
    // 4. Capacitor varlık kontrolü (window seviyesinde)
    else if (typeof window.Capacitor !== 'undefined') {
      this.state.isNative = true;
      console.log("[ORBIS] Native platform tespit edildi (window.Capacitor)");
    }
    // 5. WebView kontrolü - navigator.webdriver false ise WebView olabilir
    else if (navigator.webdriver === false && /mobile|webview/i.test(navigator.userAgent)) {
      this.state.isNative = true;
      console.log("[ORBIS] Native platform tespit edildi (WebView)");
    }
    else {
      console.log("[ORBIS] Web platform");
      this.state.isNative = false;
    }

    // Native ise AdMob'u başlat
    if (this.state.isNative) {
      this.initAdMob();
      this.requestNotificationPermission();

      // ═══════════════════════════════════════════════════════════════
      // CAPACITOR BROWSER OAUTH CALLBACK LISTENER
      // Native Google Sign-In başarısız olduğunda Browser OAuth flow
      // kullanılır. Browser plugin'den dönen callback'i handle et.
      // ═══════════════════════════════════════════════════════════════
      this.initBrowserOAuthCallback();
    } else {
      // Web'de de AdMob'u dene (bazı WebView'lar Capacitor olmadan da AdMob çalıştırabilir)
      try { this.initAdMob(); } catch(e) { /* sessiz */ }
    }

    // UI güncelle
    this.updateUI();

    console.log("[ORBIS] Durum:", this.getStatusSummary());

    // User properties ayarla
    this.setUserProperties({
      user_type: this.state.isPremium ? "premium" : "free",
      credits_available: this.state.credits,
      platform: this.state.isNative ? "mobile" : "web",
      install_date: this.state.installDate || "unknown",
    });

    // GA: Uygulama başlatma event'i
    this.trackEvent("app_start", {
      platform: this.state.isNative ? "native" : "web",
      is_premium: this.state.isPremium,
      credits: this.state.credits,
      total_analyses: this.state.totalAnalyses || 0,
    });
  },

  // ═══════════════════════════════════════════════════════════════
  // GOOGLE ANALYTICS TRACKING
  // ═══════════════════════════════════════════════════════════════

  /**
   * Google Analytics Event Gönder
   * @param {string} eventName - Event adı
   * @param {object} params - Event parametreleri
   */
  trackEvent(eventName, params = {}) {
    try {
      const enrichedParams = {
        ...params,
        timestamp: new Date().toISOString(),
        user_type: this.state.isPremium ? "premium" : "free",
        platform: this.state.isNative ? "mobile" : "web",
        session_id: this.getSessionId(),
      };

      // Google Analytics
      if (typeof gtag === "function") {
        gtag("event", eventName, enrichedParams);
        console.log(`[GA4] Event: ${eventName}`, enrichedParams);
      }

      // Firebase Analytics (native only)
      if (this.state.isNative && typeof Capacitor !== "undefined") {
        try {
          const { FirebaseAnalytics } = Capacitor.Plugins;
          if (FirebaseAnalytics) {
            FirebaseAnalytics.logEvent({
              name: eventName,
              params: this.sanitizeFirebaseParams(enrichedParams),
            });
            console.log(`[Firebase] Event: ${eventName}`);
          }
        } catch (fbError) {
          console.log("[Firebase] Analytics not available:", fbError.message);
        }
      }
    } catch (error) {
      console.error("[GA] Event tracking error:", error);
    }
  },

  /**
   * Firebase için parametre temizleme (max 100 karakter)
   */
  sanitizeFirebaseParams(params) {
    const sanitized = {};
    for (const [key, value] of Object.entries(params)) {
      if (typeof value === "string" && value.length > 100) {
        sanitized[key] = value.substring(0, 97) + "...";
      } else if (typeof value === "object") {
        sanitized[key] = JSON.stringify(value).substring(0, 100);
      } else {
        sanitized[key] = value;
      }
    }
    return sanitized;
  },

  /**
   * Session ID oluştur/al
   */
  getSessionId() {
    let sessionId = sessionStorage.getItem("orbis_session_id");
    if (!sessionId) {
      sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      sessionStorage.setItem("orbis_session_id", sessionId);
    }
    return sessionId;
  },

  /**
   * User properties ayarla
   */
  setUserProperties(properties) {
    try {
      if (typeof gtag === "function") {
        gtag("set", "user_properties", properties);
        console.log("[GA4] User properties set:", properties);
      }

      if (this.state.isNative && typeof Capacitor !== "undefined") {
        try {
          const { FirebaseAnalytics } = Capacitor.Plugins;
          if (FirebaseAnalytics) {
            for (const [key, value] of Object.entries(properties)) {
              FirebaseAnalytics.setUserProperty({ name: key, value: String(value) });
            }
          }
        } catch (fbError) {
          console.log("[Firebase] setUserProperty failed:", fbError.message);
        }
      }
    } catch (error) {
      console.error("[GA] User properties error:", error);
    }
  },

  /**
   * Conversion tracking
   */
  trackConversion(conversionType, value = 0, currency = "TRY") {
    this.trackEvent("conversion", {
      conversion_type: conversionType,
      value: value,
      currency: currency,
    });

    // Enhanced ecommerce için
    if (typeof gtag === "function" && value > 0) {
      gtag("event", "purchase", {
        transaction_id: `txn_${Date.now()}`,
        value: value,
        currency: currency,
        items: [
          {
            item_id: conversionType,
            item_name: conversionType,
            price: value,
            quantity: 1,
          },
        ],
      });
    }
  },

  /**
   * Error tracking
   */
  trackError(error, context = {}) {
    const errorData = {
      error_message: error.message || String(error),
      error_stack: error.stack ? error.stack.substring(0, 500) : "N/A",
      error_context: JSON.stringify(context).substring(0, 200),
      page_url: window.location.href,
    };

    this.trackEvent("app_error", errorData);

    console.error("[ORBIS] Error tracked:", errorData);
  },

  /**
   * Funnel tracking
   */
  trackFunnelStep(funnelName, stepName, stepNumber) {
    this.trackEvent("funnel_step", {
      funnel_name: funnelName,
      step_name: stepName,
      step_number: stepNumber,
    });
  },

  /**
   * Sayfa görüntüleme (SPA için)
   * @param {string} pagePath - Sayfa yolu
   * @param {string} pageTitle - Sayfa başlığı
   */
  trackPageView(pagePath, pageTitle) {
    try {
      if (typeof gtag === "function") {
        gtag("event", "page_view", {
          page_path: pagePath,
          page_title: pageTitle,
        });
        console.log(`[GA] Page view: ${pagePath}`);
      }
    } catch (error) {
      console.error("[GA] Page view tracking error:", error);
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // STATE YÖNETİMİ
  // ═══════════════════════════════════════════════════════════════

  loadState() {
    try {
      const saved = localStorage.getItem("orbis_monetization");
      if (saved) {
        const data = JSON.parse(saved);
        this.state = { ...this.state, ...data };
      }

      // İlk kurulum tarihi yoksa kaydet
      if (!this.state.installDate) {
        this.state.installDate = new Date().toISOString().split("T")[0];
        this.saveState();
      }
    } catch (e) {
      console.error("[ORBIS] State yükleme hatası:", e);
    }
  },

  saveState() {
    try {
      localStorage.setItem("orbis_monetization", JSON.stringify(this.state));
    } catch (e) {
      console.error("[ORBIS] State kaydetme hatası:", e);
    }
  },

  checkDailyReset() {
    const today = new Date().toISOString().split("T")[0];

    if (this.state.lastUsageDate !== today) {
      // Yeni gün - sayaçları sıfırla
      this.state.todayUsage = 0;
      this.state.todayAdsWatched = 0;
      this.state.lastUsageDate = today;
      this.saveState();
      console.log("[ORBIS] Günlük sayaçlar sıfırlandı");
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // BİLDİRİM İZNİ
  // ═══════════════════════════════════════════════════════════════

  async requestNotificationPermission() {
    // Daha önce sorulmuş mu kontrol et
    const alreadyAsked = localStorage.getItem("orbis_notification_asked");
    if (alreadyAsked) {
      console.log("[ORBIS] Bildirim izni daha önce soruldu");
      return;
    }

    // 2 saniye bekle (uygulama açılsın)
    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Güzel bir modal göster
    this.showNotificationPermissionModal();
  },

  showNotificationPermissionModal() {
    // Modal HTML oluştur
    const modalHTML = `
      <div id="notification-permission-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
        <div class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-6 w-full max-w-sm border border-white/10 shadow-2xl animate-fade-in">
          <div class="text-center mb-6">
            <div class="w-16 h-16 bg-primary/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <span class="material-icons-round text-4xl text-primary">notifications_active</span>
            </div>
            <h3 class="text-xl font-bold text-white mb-2">Bildirimleri Aç</h3>
            <p class="text-sm text-slate-400 leading-relaxed">
              Günlük burç yorumları, önemli transit geçişleri ve kişisel kozmik uyarılar için bildirimleri açın.
            </p>
          </div>
          
          <div class="space-y-3 mb-6">
            <div class="flex items-center gap-3 p-3 bg-white/5 rounded-xl">
              <span class="material-icons-round text-accent">wb_sunny</span>
              <span class="text-xs text-slate-300">Günlük burç yorumları</span>
            </div>
            <div class="flex items-center gap-3 p-3 bg-white/5 rounded-xl">
              <span class="material-icons-round text-yellow-400">stars</span>
              <span class="text-xs text-slate-300">Önemli transit geçişleri</span>
            </div>
            <div class="flex items-center gap-3 p-3 bg-white/5 rounded-xl">
              <span class="material-icons-round text-pink-400">favorite</span>
              <span class="text-xs text-slate-300">Kişisel kozmik uyarılar</span>
            </div>
          </div>
          
          <div class="space-y-2">
            <button id="accept-notif-btn" class="w-full py-4 bg-primary hover:bg-primary/90 text-white font-bold rounded-2xl transition-all active:scale-95">
              Bildirimleri Aç
            </button>
            <button id="decline-notif-btn" class="w-full py-3 text-slate-400 hover:text-white text-sm transition-colors">
              Şimdi Değil
            </button>
          </div>
        </div>
      </div>
    `;

    // Modal'ı body'e ekle
    document.body.insertAdjacentHTML("beforeend", modalHTML);

    // CSP-uyumlu: inline onclick yerine addEventListener
    document.getElementById("accept-notif-btn")?.addEventListener("click", () => this.acceptNotifications());
    document.getElementById("decline-notif-btn")?.addEventListener("click", () => this.declineNotifications());
  },

  async acceptNotifications() {
    // Modal'ı kapat
    document.getElementById("notification-permission-modal")?.remove();
    localStorage.setItem("orbis_notification_asked", "true");

    try {
      // Capacitor PushNotifications varsa kullan (Native Android/iOS)
      if (
        typeof Capacitor !== "undefined" &&
        Capacitor.Plugins.PushNotifications
      ) {
        const { PushNotifications } = Capacitor.Plugins;

        const result = await PushNotifications.requestPermissions();
        console.log("[ORBIS] Push permission result:", result);

        if (result.receive === "granted") {
          // Token alındığında listener
          PushNotifications.addListener("registration", async (token) => {
            console.log("[ORBIS] FCM Token:", token.value);

            // Token'ı backend'e kaydet ve topic'e subscribe et
            await this.registerFCMToken(token.value, "android");
          });

          // Hata listener
          PushNotifications.addListener("registrationError", (error) => {
            console.error("[ORBIS] FCM Registration error:", error);
          });

          // Bildirim geldiğinde (foreground)
          PushNotifications.addListener(
            "pushNotificationReceived",
            (notification) => {
              console.log("[ORBIS] Push received:", notification);
              // Foreground'da bildirim göster
              this.showInAppNotification(notification.title, notification.body);
            }
          );

          // Bildirime tıklandığında
          PushNotifications.addListener(
            "pushNotificationActionPerformed",
            (notification) => {
              console.log("[ORBIS] Push action:", notification);
            }
          );

          await PushNotifications.register();
          console.log("[ORBIS] Push notifications registered");
        }
      } else if ("Notification" in window && "serviceWorker" in navigator) {
        // Web Push fallback
        const permission = await Notification.requestPermission();
        console.log("[ORBIS] Web notification permission:", permission);

        if (permission === "granted") {
          // Firebase Web Push için messaging kullan
          await this.initWebPush();
        }
      }
    } catch (error) {
      console.error("[ORBIS] Notification permission error:", error);
    }
  },

  async registerFCMToken(token, platform) {
    try {
      // Backend'e token kaydet
      const response = await fetch("/api/fcm/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: token,
          platform: platform,
          topics: ["all_users"], // Varsayılan topic'lere abone ol
        }),
      });

      const data = await response.json();
      console.log("[ORBIS] FCM token registered:", data);

      // Local'e de kaydet
      localStorage.setItem("orbis_fcm_token", token);
    } catch (error) {
      console.error("[ORBIS] FCM token registration error:", error);
    }
  },

  async initWebPush() {
    try {
      // Firebase Web SDK varsa kullan
      if (typeof firebase !== "undefined" && firebase.messaging) {
        const messaging = firebase.messaging();
        const token = await messaging.getToken({
          vapidKey: "YOUR_VAPID_KEY", // Firebase Console'dan al
        });

        if (token) {
          await this.registerFCMToken(token, "web");
        }
      }
    } catch (error) {
      console.error("[ORBIS] Web push init error:", error);
    }
  },

  showInAppNotification(title, body) {
    // Foreground'da güzel bir in-app notification göster
    const notifHTML = `
      <div id="in-app-notif" class="fixed top-4 left-4 right-4 z-[300] animate-slide-down">
        <div class="bg-slate-800/95 backdrop-blur-xl rounded-2xl p-4 border border-white/10 shadow-2xl flex items-start gap-3">
          <div class="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center flex-shrink-0">
            <span class="material-icons-round text-primary">notifications</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-bold text-sm text-white">${title || "ORBIS"}</div>
            <p class="text-xs text-slate-400 mt-1 line-clamp-2">${
              body || ""
            }</p>
          </div>
          <button id="notif-close-btn" class="text-slate-500 hover:text-white">
            <span class="material-icons-round text-lg">close</span>
          </button>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML("beforeend", notifHTML);

    // CSP-uyumlu: close button addEventListener
    document.getElementById("notif-close-btn")?.addEventListener("click", () => {
      document.getElementById("in-app-notif")?.remove();
    });

    // 5 saniye sonra otomatik kapat
    setTimeout(() => {
      document.getElementById("in-app-notif")?.remove();
    }, 5000);
  },

  declineNotifications() {
    // Modal'ı kapat
    document.getElementById("notification-permission-modal")?.remove();
    localStorage.setItem("orbis_notification_asked", "true");
    console.log("[ORBIS] Bildirimler reddedildi");
  },

  // ═══════════════════════════════════════════════════════════════
  // DURUM SORGULAMA
  // ═══════════════════════════════════════════════════════════════

  isFirstDay() {
    const today = new Date().toISOString().split("T")[0];
    return this.state.installDate === today;
  },

  getDailyLimit() {
    if (this.state.isPremium) {
      return Infinity; // Premium için limit yok (kredi varsa)
    }
    return this.isFirstDay()
      ? this.CONFIG.FREE_FIRST_DAY_TOTAL
      : this.CONFIG.FREE_DAILY_LIMIT;
  },

  getRemainingToday() {
    if (this.state.isPremium) {
      return "∞"; // Sınırsız
    }
    return "Reklam ile sınırsız"; // Reklam izleyerek sınırsız
  },

  needsAd() {
    if (this.state.isPremium) return false;
    // ÜCRETSİZ KULLANICI = HER ZAMAN REKLAM GEREKLİ
    return true;
  },

  canAnalyze() {
    // Premium: her zaman
    // Ücretsiz: her zaman (reklamla)
    return true;
  },

  getStatusSummary() {
    return {
      isPremium: this.state.isPremium,
      credits: this.state.credits,
      isFirstDay: this.isFirstDay(),
      todayUsage: this.state.todayUsage,
      remaining: this.getRemainingToday(),
      needsAd: this.needsAd(),
    };
  },

  // ═══════════════════════════════════════════════════════════════
  // ANALİZ İSTEĞİ
  // ═══════════════════════════════════════════════════════════════

  async requestAnalysis(onSuccess, onCancel) {
    console.log("[ORBIS] Analiz isteği başladı...");

    // ⚠️ KRİTİK: Her analiz öncesi backend'den premium durumunu doğrula
    // localStorage'da eski premium kalmış olabilir
    if (this.state.isPremium) {
      await this.verifyPremiumWithBackend();
    }

    if (!this.canAnalyze()) {
      console.log("[ORBIS] Analiz yapılamaz - limit aşıldı");

      // GA: Limit aşıldı event'i
      this.trackEvent("analysis_limit_reached", {
        today_usage: this.state.todayUsage,
        daily_limit: this.getDailyLimit(),
      });

      this.showLimitReachedModal();
      if (onCancel) {
        console.log("[ORBIS] Calling onCancel...");
        onCancel();
      }
      return;
    }

    // Premium kullanıcı - reklamsız, sınırsız
    if (this.state.isPremium) {
      this.state.todayUsage++;
      this.state.totalAnalyses++;
      this.saveState();
      this.updateUI();

      // GA: Premium analiz event'i
      this.trackEvent("analysis_completed", {
        analysis_type: "premium",
        total_analyses: this.state.totalAnalyses,
      });

      console.log("[ORBIS] Premium analiz");
      if (onSuccess) {
        console.log("[ORBIS] Calling onSuccess (premium)...");
        onSuccess();
      }
      return;
    }

    // Ücretsiz kullanıcı - reklam gerekiyor mu?
    if (this.needsAd()) {
      console.log("[ORBIS] Reklam gerekiyor...");
      // Reklam izletmemiz lazım
      const adResult = await this.showRewardedAdFlow();

      if (adResult && adResult.success) {
        this.state.todayUsage++;
        this.state.todayAdsWatched++;
        this.state.totalAnalyses++;
        this.saveState();
        this.updateUI();

        // Her 3 analizde interstitial göster
        this.showInterstitialAd();

        // 🆕 REKLAM İZLENDİ - Backend'e kaydet
        this.recordAdWatchToBackend();

        // GA: Reklamlı analiz event'i
        this.trackEvent("analysis_completed", {
          analysis_type: "with_ad",
          ads_watched_today: this.state.todayAdsWatched,
          total_analyses: this.state.totalAnalyses,
        });

        console.log(
          "[ORBIS] Reklamlı analiz, bugünkü kullanım:",
          this.state.todayUsage
        );
        if (onSuccess) {
          console.log("[ORBIS] Calling onSuccess (ad watched)...");
          onSuccess();
        }
      } else {
        // GA: Reklam izlenmedi event'i
        this.trackEvent("ad_skipped", {
          ad_type: "rewarded",
          reason: (adResult && adResult.reason) || "unknown",
        });

        console.log("[ORBIS] Reklam izlenmedi / başarısız. reason:", adResult && adResult.reason);
        if (onCancel) {
          console.log("[ORBIS] Calling onCancel with reason...");
          // Yeni imza: onCancel(reason) — dashboard.html bunu toast/alert göstermek için kullanır
          onCancel((adResult && adResult.reason) || "unknown");
        }
      }
    } else {
      // İlk gün, ilk 3 analiz - reklamsız
      this.state.todayUsage++;
      this.state.totalAnalyses++;
      this.saveState();
      this.updateUI();

      // GA: Ücretsiz analiz event'i
      this.trackEvent("analysis_completed", {
        analysis_type: "free_trial",
        today_usage: this.state.todayUsage,
        total_analyses: this.state.totalAnalyses,
      });

      console.log(
        "[ORBIS] Ücretsiz analiz (hoşgeldin), bugünkü kullanım:",
        this.state.todayUsage
      );

      if (onSuccess) {
        console.log("[ORBIS] Calling onSuccess (free)...");
        try {
          onSuccess();
          console.log("[ORBIS] onSuccess called successfully");
        } catch (err) {
          console.error("[ORBIS] onSuccess error:", err);
        }
      } else {
        console.error("[ORBIS] onSuccess is not defined!");
      }
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // CAPACITOR BROWSER OAUTH CALLBACK
  // ═══════════════════════════════════════════════════════════════
  //
  // Native Google Sign-In başarısız olduğunda (Play Services yok,
  // SHA-1 uyumsuz vs.) Firebase _signInWithBrowserOAuth fallback'i
  // Capacitor Browser ile OAuth akışı başlatır. Browser OAuth
  // tamamlanıp uygulamaya geri döndüğünde bu listener yakalar.
  //
  initBrowserOAuthCallback() {
    try {
      const isNative =
        typeof Capacitor !== "undefined" && Capacitor.isNativePlatform();
      if (!isNative) return;

      const Browser =
        (Capacitor.Plugins && Capacitor.Plugins.Browser) ||
        (window.Plugins && window.Plugins.Browser);
      if (!Browser) {
        console.warn("[ORBIS] Browser plugin yok, OAuth callback listener kurulamiyor");
        return;
      }

      // 'browserFinished' veya 'appUrlOpen' event'i ile OAuth
      // callback'i handle et. Capacitor 6+'da App.addListener
      // 'appUrlOpen' önerilir.
      if (typeof Capacitor.Plugins.App !== "undefined") {
        const App = Capacitor.Plugins.App;
        App.addListener("appUrlOpen", (event) => {
          console.log("[ORBIS] App URL açıldı (OAuth callback?):", event.url);
          // Firebase signInWithRedirect kendi getRedirectResult()'ı
          // init() zaten handle ediyor (OrbisFirebase.init içinde)
          // Burada ek bir şey yapmamıza gerek yok, sadece log.
        });
        console.log("[ORBIS] App.appUrlOpen listener kuruldu (OAuth callback için)");
      }

      // Browser plugin finished event'i
      Browser.addListener("browserFinished", () => {
        console.log("[ORBIS] Browser kapandı (OAuth tamamlandı veya iptal)");
      });
      Browser.addListener("urlChangeEvent", (event) => {
        console.log("[ORBIS] Browser URL değişti:", event.url);
      });
    } catch (e) {
      console.warn("[ORBIS] initBrowserOAuthCallback hatası:", e);
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // ADMOB
  // ═══════════════════════════════════════════════════════════════

  async initAdMob() {
    if (!this.state.isNative) return;

    try {
      const { AdMob } = Capacitor.Plugins;
      if (!AdMob) {
        console.warn("[ORBIS] AdMob plugin yüklü değil — native tarafta @capacitor-community/admob kurulu olmalı");
        return;
      }
      const adConfig = this._getAdmob();

      // ⚠️ KRİTİK: AdMob.initialize() zorunlu. Bu çağrılmadan prepare/show
      // sessizce başarısız olur → AdMob panelinde "0 istek" gözükür.
      // initializeForTesting:true, prod reklam yerine test reklamı yükler
      // ve NO_FILL hatasına neden olur — bu yüzden false.
      await AdMob.initialize({
        // initializeForTesting:true → test reklam (NO_FILL)
        // initializeForTesting:false → gerçek reklam (production)
        initializeForTesting: this.CONFIG.IS_TESTING,
        // TagForChildDirectedTreatment: TR mevzuatı gereği çocuk yönelimli
        // değiliz → false. Yanlışlıkla true yapılırsa AdMob tüm reklamları
        // reddeder → 0 etkin kalır.
        tagForChildDirectedTreatment: false,
        // tagForUnderAgeOfConsent: aynı şekilde false
        tagForUnderAgeOfConsent: false,
      });

      console.log("[ORBIS] ✅ AdMob.initialize başarılı (appId=" + adConfig.APP_ID + ")");

      // ⚠️ KRİTİK: AppId sadece AndroidManifest.xml'de tanımlı olur; burada
      // tekrar set etmek gerekmez. Ama config sanity check yapalım:
      if (!adConfig.APP_ID || !adConfig.APP_ID.startsWith("ca-app-pub-")) {
        console.error("[ORBIS] ❌ Geçersiz AdMob APP_ID:", adConfig.APP_ID);
        return;
      }

      // iOS 14+ ATT (App Tracking Transparency) — ayrı method.
      // Android'de silent ignore. iOS'ta popup gösterir.
      // Sadece native iOS'ta çalışır; Android'de plugin "unimplemented" döner.
      try {
        if (typeof AdMob.trackingAuthorizationStatus === "function") {
          const tracking = await AdMob.trackingAuthorizationStatus();
          if (tracking?.status === "notDetermined" && typeof AdMob.requestTrackingAuthorization === "function") {
            await AdMob.requestTrackingAuthorization();
          }
        }
      } catch (e) {
        // iOS dışı platform — silent ignore
        console.log("[ORBIS] ATT atlandı (Android veya unsupported):", e?.message || "");
      }

      // GDPR/KVKK: TR kullanıcıları için non-personalized ads default.
      // consentStatus='NON_PERSONALIZED' veya 'UNKNOWN' ise NPA kullan.
      // (Detaylı consent dialog Options sayfasında gösterilebilir.)
      try {
        if (typeof AdMob.requestConsentInfo === "function") {
          const consent = await AdMob.requestConsentInfo({});
          console.log("[ORBIS] Consent status:", consent?.status);
          this._adConsentStatus = consent?.status || "UNKNOWN";
        }
      } catch (e) {
        console.log("[ORBIS] Consent info atlandı:", e?.message || e);
        this._adConsentStatus = "UNKNOWN";
      }

      // Reklamları önceden yükle
      await this.loadRewardedAd();
      await this.loadInterstitialAd();

      // Premium değilse banner göster
      if (!this.state.isPremium) {
        await this.showBanner();
      }
    } catch (error) {
      console.error("[ORBIS] AdMob başlatma hatası:", error);
    }
  },

  async showBanner() {
    if (!this.state.isNative || this.state.isPremium) return;

    try {
      const { AdMob } = Capacitor.Plugins;
      const adConfig = this._getAdmob();

      await AdMob.showBanner({
        adId: adConfig.BANNER,
        adSize: "ADAPTIVE_BANNER",
        position: "BOTTOM_CENTER",
        margin: 0,
        isTesting: this.CONFIG.IS_TESTING,
      });

      // Banner için padding (banner 60px + bottom nav 80px = 140px)
      document.body.style.paddingBottom = "140px";

      // Bottom nav'ı yukarı kaydır
      const bottomNav = document.querySelector("nav.fixed.bottom-0");
      if (bottomNav) {
        bottomNav.style.bottom = "60px";
      }

      // GA: Banner gösterildi event'i
      this.trackEvent("ad_impression", {
        ad_type: "banner",
        ad_position: "bottom",
      });

      console.log("[ORBIS] Banner gösterildi");
    } catch (error) {
      console.error("[ORBIS] Banner hatası:", error);
    }
  },

  async hideBanner() {
    if (!this.state.isNative) return;

    try {
      const { AdMob } = Capacitor.Plugins;
      await AdMob.hideBanner();
      document.body.style.paddingBottom = "0";

      // Bottom nav'ı eski konumuna döndür
      const bottomNav = document.querySelector("nav.fixed.bottom-0");
      if (bottomNav) {
        bottomNav.style.bottom = "0";
      }
    } catch (error) {
      console.error("[ORBIS] Banner gizleme hatası:", error);
    }
  },

  // Interstitial (tam ekran) reklam
  async loadInterstitialAd() {
    if (!this.state.isNative) return;

    try {
      const { AdMob } = Capacitor.Plugins;
      const adConfig = this._getAdmob();

      await AdMob.prepareInterstitial({
        adId: adConfig.INTERSTITIAL,
        isTesting: this.CONFIG.IS_TESTING,
      });

      console.log("[ORBIS] Interstitial yüklendi");
    } catch (error) {
      console.error("[ORBIS] Interstitial yükleme hatası:", error);
    }
  },

  async showInterstitialAd() {
    if (!this.state.isNative || this.state.isPremium) return;

    // Her X analizde bir göster
    if (this.state.totalAnalyses % this.CONFIG.INTERSTITIAL_INTERVAL !== 0) {
      return;
    }

    try {
      const { AdMob } = Capacitor.Plugins;
      await AdMob.showInterstitial();

      // GA: Interstitial gösterildi event'i
      this.trackEvent("ad_impression", {
        ad_type: "interstitial",
        total_analyses: this.state.totalAnalyses,
      });

      console.log("[ORBIS] Interstitial gösterildi");

      // Yeni interstitial yükle
      this.loadInterstitialAd();
    } catch (error) {
      console.error("[ORBIS] Interstitial gösterme hatası:", error);
    }
  },

  async loadRewardedAd() {
    if (!this.state.isNative) return;

    try {
      const { AdMob } = Capacitor.Plugins;
      const adConfig = this._getAdmob();

      // 🆕 ANALIZ birimini tercih et, yoksa eski REWARDED kullan
      const rewardedAdId = adConfig.REWARDED_ANALIZ || adConfig.REWARDED;

      await AdMob.prepareRewardVideoAd({
        adId: rewardedAdId,
        isTesting: this.CONFIG.IS_TESTING,
      });

      console.log(`[ORBIS] Rewarded ad yüklendi (ID: ${rewardedAdId})`);
    } catch (error) {
      console.error("[ORBIS] Rewarded ad yükleme hatası:", error);
    }
  },

  async showRewardedAdFlow() {
    // WEB PLATFORM: modal popup ile reklam deneyimi
    if (!this.state.isNative) {
      console.log("[ORBIS] Web platform - reklam modal gösteriliyor...");
      return await this.showRewardedAd();
    }

    // NATIVE PLATFORM: ADMOB reklamı göster
    console.log("[ORBIS] Native platform - rewarded ad gösteriliyor...");
    return await this.showRewardedAd();
  },

  async showRewardedAd() {
    return new Promise(async (resolve) => {
      try {
        // ═════════════════════════════════════════════════════════
        // WEB / WEBVIEW PLATFORM
        // ═════════════════════════════════════════════════════════
        if (!this.state.isNative) {
          console.log("[ORBIS] Web platform - reklam modal gösteriliyor...");
          
          // Modal HTML oluştur
          const modal = document.createElement('div');
          modal.id = 'ad-reward-overlay';
          modal.style.cssText = 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.8);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)';
          modal.innerHTML = `
            <div class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-6 w-full max-w-sm mx-4 border border-white/10 shadow-2xl text-center animate-fade-in">
              <div class="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center">
                <span class="material-icons-round text-4xl text-primary">play_circle</span>
              </div>
              <h3 class="text-xl font-bold text-white mb-2">Reklam İzle</h3>
              <p class="text-sm text-slate-400 mb-6 leading-relaxed">
                AI yorumun kilidini acmak icin lutfen kisa bir reklam izleyin.
                Uygulamamiz tamamen ucretsizdir.
              </p>
              <div class="flex flex-col gap-3">
                <button id="ad-reward-watch-btn" class="w-full py-4 bg-primary hover:bg-primary/90 text-white font-bold rounded-2xl transition-all active:scale-95 flex items-center justify-center gap-2">
                  <span class="material-icons-round">play_arrow</span>
                  Reklam İzle ve Devam Et
                </button>
                <button id="ad-reward-cancel-btn" class="w-full py-3 text-slate-500 hover:text-slate-300 text-sm transition-colors">
                  Vazgeç
                </button>
              </div>
            </div>
          `;
          document.body.appendChild(modal);

          // Buton event'leri
          const watchBtn = document.getElementById('ad-reward-watch-btn');
          const cancelBtn = document.getElementById('ad-reward-cancel-btn');

          // İzle butonu
          watchBtn.addEventListener('click', () => {
            console.log("[ORBIS] Web reklam izlendi - analiz devam");
            this.trackEvent("ad_impression", { ad_type: "rewarded_web" });
            this.trackEvent("ad_reward", { ad_type: "rewarded_web", reward_type: "analysis_credit" });
            modal.remove();
            resolve({ success: true, reason: null });
          });

          // Premium butonu kaldirildi (premium artik yok).
          // Geriye uyumluluk: eski 'ad-reward-premium-btn' varsa tiklama no-op yapar.
          const legacyPremiumBtn = document.getElementById('ad-reward-premium-btn');
          if (legacyPremiumBtn) {
            legacyPremiumBtn.addEventListener('click', () => {
              console.info("[ORBIS] Legacy premium buton ignored (premium removed).");
              modal.remove();
              resolve({ success: false, reason: "user_cancelled" });
            });
          }

          // İptal butonu
          cancelBtn.addEventListener('click', () => {
            console.log("[ORBIS] Web reklam iptal edildi");
            modal.remove();
            resolve({ success: false, reason: "user_cancelled" });
          });

          return;
        }

        // ═════════════════════════════════════════════════════════
        // NATIVE PLATFORM - Capacitor AdMob ile reklam
        // ═════════════════════════════════════════════════════════
        const { AdMob } = Capacitor.Plugins;
        
        let rewarded = false;
        let notified = false; // resolve'in 2 kere çağrılmasını engelle
        let cleanupFns = [];
        
        const cleanup = () => {
          cleanupFns.forEach(fn => { try { fn(); } catch(e) {} });
          cleanupFns = [];
        };

        // smartResolve: AdMob reason + native-to-web fallback akıllı çözümleyici
        // Başarıda {success:true, reason:null}; başarısızlıkta {success:false, reason}
        // Native AdMob başarısız olduğunda (no-fill / timeout / load error) web modal
        // fallback dener — kök neden çözümü.
        const smartResolve = (success, reason) => {
          if (notified) return;
          notified = true;
          cleanup();
          // Yeni reklam yükle
          this.loadRewardedAd();

          // ⚠️ KRİTİK: Native AdMob başarısızsa web modal fallback tetikle.
          // Genişletilmiş whitelist: -1 (NO_FILL / internal), 0, 1, 2, 3, tüm sayılar
          // ve "ad_load_failed:*", "ad_show_failed:*", "ad_timeout" hepsi.
          const isAdLoadFailed = typeof reason === "string" && reason.startsWith("ad_load_failed");
          const isAdShowFailed = typeof reason === "string" && reason.startsWith("ad_show_failed");
          const isAdTimeout = reason === "ad_timeout";

          const needsFallback =
            success === false &&
            this.state.isNative &&
            (isAdLoadFailed || isAdShowFailed || isAdTimeout);

          if (needsFallback) {
            console.log(
              "[ORBIS] AdMob native başarısız, web modal fallback deneniyor. reason:",
              reason
            );
            // Kullanıcıya bilgi ver — neden reklam gösterilemedi
            this.showAdLoadError(reason);
            // Web modal fallback dene (async). Kullanıcı seçerse success=true döner.
            this.showWebRewardedFallback(reason)
              .then((webResult) => {
                if (webResult === true) {
                  setTimeout(
                    () =>
                      resolve({
                        success: true,
                        reason: "web_fallback",
                      }),
                    200
                  );
                } else {
                  setTimeout(
                    () =>
                      resolve({
                        success: false,
                        reason: "user_cancelled",
                      }),
                    200
                  );
                }
              })
              .catch((err) => {
                console.error("[ORBIS] Web fallback hata:", err);
                setTimeout(
                  () => resolve({ success: false, reason }),
                  200
                );
              });
            return;
          }

          setTimeout(
            () => resolve({ success: success, reason: success ? null : reason }),
            200
          );
        };

        // Ödül kazanıldı
        const rl = await AdMob.addListener("onRewardedVideoAdReward", () => {
          console.log("[ORBIS] ✅ Ödül kazanıldı!");
          rewarded = true;
          this.trackEvent("ad_reward", { ad_type: "rewarded", reward_type: "analysis_credit" });
        });
        cleanupFns.push(() => rl.remove());

        // Reklam kapatıldı
        const dl = await AdMob.addListener("onRewardedVideoAdDismissed", () => {
          console.log("[ORBIS] Reklam kapatıldı, ödül:", rewarded);
          smartResolve(rewarded, rewarded ? null : "user_dismissed_without_reward");
        });
        cleanupFns.push(() => dl.remove());

        // Yüklenemedi
        const fl = await AdMob.addListener("onRewardedVideoAdFailedToLoad", (error) => {
          console.error("[ORBIS] Ad yüklenemedi:", error);
          const code = (error && (error.code !== undefined ? error.code : error)) || "unknown";
          smartResolve(false, "ad_load_failed:" + code);
        });
        cleanupFns.push(() => fl.remove());

        // Gösterilemedi
        const fs = await AdMob.addListener("onRewardedVideoAdFailedToShow", (error) => {
          console.error("[ORBIS] Ad gösterilemedi:", error);
          const code = (error && (error.code !== undefined ? error.code : error)) || "unknown";
          smartResolve(false, "ad_show_failed:" + code);
        });
        cleanupFns.push(() => fs.remove());

        // Timeout güvenliği - 30 saniye sonra timeout
        const timeoutId = setTimeout(() => {
          if (!notified) {
            console.warn("[ORBIS] Ad timeout - 30sn doldu");
            smartResolve(false, "ad_timeout");
          }
        }, 30000);
        cleanupFns.push(() => clearTimeout(timeoutId));

        console.log("[ORBIS] Rewarded video gösteriliyor...");
        this.trackEvent("ad_impression", { ad_type: "rewarded" });
        await AdMob.showRewardVideoAd();

      } catch (error) {
        console.error("[ORBIS] Rewarded ad hatası:", error);
        // Hata durumunda bile web'de bir modal göster
        if (!this.state.isNative) {
          try { document.getElementById('ad-reward-overlay')?.remove(); } catch(e) {}
          // Basit confirm ile dene
          const retry = confirm("📺 Reklam gösterilemedi. Tekrar dene?");
          resolve({ success: retry, reason: retry ? "web_retry" : "user_cancelled" });
        } else {
          if (!notified) {
            // Native throw — fallback dene
            const errMsg = (error && (error.message || String(error))) || "unknown";
            smartResolve(false, "ad_throw:" + errMsg);
          }
        }
      }
    });
  },

  // ═══════════════════════════════════════════════════════════════
  // PREMIUM & KREDİ - KALDIRILDI
  // ═══════════════════════════════════════════════════════════════

  showPremiumPackages() {
    // DEPRECATED: Premium kaldirildi. Uygulama tamamen ucretsiz.
    console.info("[ORBIS] showPremiumPackages called but premium is removed.");
    if (typeof alert !== "undefined") {
      alert("Uygulamamiz tamamen ucretsizdir. Premium satin alma ozellikleri kaldirildi.");
    }
  },

  async purchasePremium(index_or_pkg = 0) {
    // DEPRECATED: Premium satin alma kaldirildi. Uygulama tamamen ucretsiz.
    console.info("[ORBIS] purchasePremium called but premium is removed:", index_or_pkg);
    if (typeof alert !== "undefined") {
      alert("Premium satin alma kaldirildi. Uygulama tamamen ucretsizdir.");
    }
    return false;
  },

  // ═══════════════════════════════════════════════════════════════
  // UI & MODALS
  // ═══════════════════════════════════════════════════════════════

  showLimitReachedModal() {
    // Herkes ucretsiz — sadece reklam izleme uyarisi
    if (typeof alert !== "undefined") {
      alert("Analiz icin lutfen kisa bir reklam izleyin.");
    }
  },

  /**
   * AdMob hata nedenini kullanıcı dostu Türkçe mesaja çevirir.
   * dashboard.html'deki cancelCallback bunu kullanır.
   * @param {string} reason - showRewardedAd'dan dönen reason string
   * @returns {string|null} - Mesaj veya bilinmeyen nedenler için null
   */
  explainAdFail(reason) {
    if (!reason) return null;

    // En yaygın nedenler önce
    if (reason === "ad_timeout") {
      return "Reklam 30 saniye içinde yüklenemedi. İnternet bağlantınızı kontrol edin ve tekrar deneyin.";
    }
    if (reason === "ad_load_failed:3") {
      return "Reklam envanteri şu an bu cihaz için boş. Birkaç saat sonra tekrar deneyin veya Premium'a geçerek reklamsız kullanın.";
    }
    if (reason === "ad_load_failed:0") {
      return "Reklam isteği başarısız oldu. İnternet bağlantınızı kontrol edin.";
    }
    if (reason === "ad_load_failed:1") {
      return "Reklam sunucusundan geçersiz yanıt alındı. Tekrar deneyin.";
    }
    if (reason === "ad_load_failed:2") {
      return "Reklam ağı bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin.";
    }
    if (reason.startsWith("ad_load_failed")) {
      return "Reklam yüklenemedi (kod: " + reason + "). Lütfen tekrar deneyin.";
    }
    if (reason.startsWith("ad_show_failed")) {
      return "Reklam gösterilemedi. Uygulamayı yeniden başlatıp tekrar deneyin.";
    }
    if (reason.startsWith("ad_throw")) {
      return "Reklam sistemi başlatılamadı. Uygulamayı kapatıp yeniden açın.";
    }
    if (reason === "user_cancelled") {
      return null; // Kullanıcı kendisi iptal etti — bilgi gösterme
    }
    if (reason === "user_dismissed_without_reward") {
      return "Reklam tam izlenmedi. Ödül kazanılamadığı için analiz başlatılamadı.";
    }
    if (reason === "premium_chosen") {
      return null; // Premium'a yönlendirildi — bilgi gösterme
    }
    if (reason === "web_retry") {
      return "Reklam gösterilemedi. Tekrar denemek istiyor musunuz?";
    }
    if (reason === "web_fallback") {
      return null; // Web fallback başarılı — bilgi gösterme
    }
    return "Reklam gösterilemedi. Lütfen tekrar deneyin. (kod: " + reason + ")";
  },

  /**
   * Üstten slide-in toast: AdMob hatasını kullanıcıya gösterir.
   * 60 sn sonra otomatik kapanır, kullanıcı da kapatabilir.
   * "Tekrar Dene" butonu formu yeniden submit eder.
   * @param {string} message - explainAdFail'den gelen mesaj
   * @param {string} reason - opsiyonel, console'a log için
   */
  showAdErrorToast(message, reason) {
    try {
      // Mevcut toast varsa kaldır
      const existing = document.getElementById("orbis-ad-error-toast");
      if (existing) existing.remove();

      const toast = document.createElement("div");
      toast.id = "orbis-ad-error-toast";
      toast.style.cssText =
        "position:fixed;top:1rem;left:1rem;right:1rem;z-index:300;transform:translateY(-220%);transition:transform 0.4s ease-out;pointer-events:none";
      toast.innerHTML =
        '<div style="pointer-events:auto" class="bg-red-500/95 backdrop-blur-sm text-white px-4 py-3 rounded-2xl shadow-2xl border border-red-400/30 flex items-center gap-3 max-w-md mx-auto">' +
        '<span class="material-icons-round text-2xl flex-shrink-0">error_outline</span>' +
        '<div class="flex-1 min-w-0">' +
        '<p class="text-sm font-bold leading-tight">Reklam Yüklenemedi</p>' +
        '<p class="text-xs opacity-90 mt-0.5 leading-snug">' +
        String(message).replace(/</g, "&lt;") +
        "</p>" +
        "</div>" +
        '<button id="orbis-toast-retry" class="bg-white/20 hover:bg-white/30 px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1 transition-colors flex-shrink-0" aria-label="Tekrar Dene">' +
        '<span class="material-icons-round text-sm">refresh</span><span>Tekrar</span>' +
        "</button>" +
        '<button id="orbis-toast-close" class="text-white/70 hover:text-white flex-shrink-0" aria-label="Kapat">' +
        '<span class="material-icons-round text-lg">close</span>' +
        "</button>" +
        "</div>";
      document.body.appendChild(toast);

      // Slide-in (çift rAF ile layout settle olduktan sonra)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          toast.style.transform = "translateY(0)";
        });
      });

      // Close handler
      const close = () => {
        toast.style.transform = "translateY(-220%)";
        setTimeout(() => {
          if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 400);
      };
      const closeBtn = document.getElementById("orbis-toast-close");
      const retryBtn = document.getElementById("orbis-toast-retry");
      if (closeBtn) closeBtn.addEventListener("click", close);
      if (retryBtn) {
        retryBtn.addEventListener("click", () => {
          close();
          // Form'u yeniden submit et
          const form = document.getElementById("orbisForm");
          if (form) {
            console.log("[ORBIS] Toast retry: form yeniden submit ediliyor");
            form.dispatchEvent(
              new Event("submit", { cancelable: true, bubbles: true })
            );
          }
        });
      }

      // 60 sn sonra otomatik kapat (güvenlik)
      setTimeout(close, 60000);
    } catch (e) {
      console.error("[ORBIS] showAdErrorToast hatası:", e);
      // Son çare: native alert
      try {
        alert("⚠️ " + message);
      } catch (_) {}
    }
  },

  /**
   * Native AdMob başarısız olduğunda web modal fallback gösterir.
   * Kullanıcı "Reklam İzle" derse true, "Vazgeç" derse false döner.
   * @param {string} reason - smartResolve'den gelen reason
   * @returns {Promise<boolean|null>} - true/false = kullanıcı seçti, null = modal oluşturulamadı
   */
  showWebRewardedFallback(reason) {
    return new Promise((resolve) => {
      try {
        // Mevcut modal varsa kaldır
        const existing = document.getElementById("ad-reward-overlay");
        if (existing) existing.remove();

        const isNoFill = reason === "ad_load_failed:3";
        const reasonText = isNoFill
          ? "Reklam envanteri şu an bu cihaz için boş. Yine de devam etmek için aşağıdan onaylayın."
          : reason === "ad_timeout"
          ? "Reklam zaman aşımına uğradı. Yine de devam etmek için aşağıdan onaylayın."
          : "Reklam yüklenemedi. Yine de devam etmek için aşağıdan onaylayın.";

        const modal = document.createElement("div");
        modal.id = "ad-reward-overlay";
        modal.style.cssText =
          "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.8);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)";
        // Premium kaldirildi: sadece 'Yine de Devam Et' ve 'Vazgeç' butonlari
        modal.innerHTML =
          '<div class="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-6 w-full max-w-sm mx-4 border border-white/10 shadow-2xl text-center animate-fade-in">' +
          '<div class="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-amber-500/30 to-orange-500/30 flex items-center justify-center">' +
          '<span class="material-icons-round text-4xl text-amber-400">info</span>' +
          "</div>" +
          '<h3 class="text-xl font-bold text-white mb-2">Reklam Gösterilemedi</h3>' +
          '<p class="text-sm text-slate-400 mb-6 leading-relaxed">' +
          reasonText +
          "</p>" +
          '<div class="flex flex-col gap-3">' +
          '<button id="ad-fallback-confirm" class="w-full py-4 bg-primary hover:bg-primary/90 text-white font-bold rounded-2xl transition-all active:scale-95 flex items-center justify-center gap-2">' +
          '<span class="material-icons-round">play_arrow</span>' +
          "Yine de Devam Et" +
          "</button>" +
          '<button id="ad-fallback-cancel" class="w-full py-3 text-slate-500 hover:text-slate-300 text-sm transition-colors">' +
          "Vazgeç" +
          "</button>" +
          "</div>" +
          "</div>";
        document.body.appendChild(modal);

        const cleanup = () => {
          if (modal.parentNode) modal.parentNode.removeChild(modal);
        };

        const confirmBtn = document.getElementById("ad-fallback-confirm");
        const cancelBtn = document.getElementById("ad-fallback-cancel");

        if (confirmBtn) {
          confirmBtn.addEventListener("click", () => {
            console.log(
              "[ORBIS] Web fallback: kullanıcı 'Yine de Devam Et' seçti"
            );
            this.trackEvent("ad_fallback_used", { reason: reason });
            cleanup();
            resolve(true);
          });
        }
        // Premium butonu kaldirildi. Geriye uyumluluk: varsa no-op.
        const legacyPremiumBtn = document.getElementById("ad-fallback-premium");
        if (legacyPremiumBtn) {
          legacyPremiumBtn.addEventListener("click", () => {
            console.info("[ORBIS] Legacy premium buton ignored (premium removed).");
            cleanup();
            resolve(false);
          });
        }
        if (cancelBtn) {
          cancelBtn.addEventListener("click", () => {
            console.log("[ORBIS] Web fallback: kullanıcı vazgeçti");
            cleanup();
            resolve(false);
          });
        }
      } catch (e) {
        console.error("[ORBIS] showWebRewardedFallback modal hatası:", e);
        resolve(null);
      }
    });
  },

  showPremiumPromo() {
    // DEPRECATED: Premium kaldirildi. Uygulama tamamen ucretsiz.
    // Geriye uyumluluk: sadece bilgilendirme.
    console.info("[ORBIS] showPremiumPromo called but premium is removed.");
    if (typeof alert !== "undefined") {
      alert("Uygulamamiz tamamen ucretsizdir. Premium satin alma kaldirildi.");
    }
  },

  updateUI() {
    // Status bar güncelle (varsa)
    const statusEl = document.getElementById("orbis-status");
    if (statusEl) {
      if (this.state.isPremium) {
        statusEl.innerHTML = `💎 Premium Aktif`;
      } else {
        const remaining = this.getRemainingToday();
        statusEl.innerHTML = `🆓 Ücretsiz | Bugün: ${remaining} hak`;
      }
    }

    // Premium badge (varsa)
    const premiumBadge = document.getElementById("premium-badge");
    if (premiumBadge) {
      premiumBadge.style.display = this.state.isPremium ? "flex" : "none";
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // TEST & DEBUG
  // ═══════════════════════════════════════════════════════════════

  resetAll() {
    if (confirm("⚠️ Tüm veriler sıfırlanacak. Emin misiniz?")) {
      localStorage.removeItem("orbis_monetization");
      location.reload();
    }
  },

  /**
   * Firebase çıkış yapıldığında local state'e dön
   */
  resetToLocal() {
    console.log("[ORBIS] Firebase çıkış - local state sıfırlanıyor");

    // Premium state'ini temizle (localStorage'da kalmış olabilir)
    this.state.isPremium = false;
    this.state.premiumPackageId = null;
    this.state.premiumExpiry = null;
    this.state.credits = 0;
    this.saveState();

    // UI güncelle
    this.updateUI();

    // Premium değilse banner göster
    if (!this.state.isPremium && this.state.isNative) {
      this.showBanner();
    }
  },

  // 🆕 Reklam izlendi - backend'e kaydet
  async recordAdWatchToBackend() {
    const deviceId = this.getDeviceId();
    const email = window.OrbisFirebase?.getCurrentUser()?.email || null;

    try {
      // 1. record_ad_watch endpoint
      const res1 = await fetch('/api/record_ad_watch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId, email: email })
      });
      const data1 = await res1.json();
      console.log("[ORBIS] ✅ Ad watch recorded to backend:", data1);
    } catch (e) {
      console.warn("[ORBIS] ⚠️ record_ad_watch failed:", e.message);
    }

    try {
      // 2. Monetization API
      const res2 = await fetch('/api/monetization/record-usage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId, email: email, feature: 'ad_watch' })
      });
      const data2 = await res2.json();
      console.log("[ORBIS] ✅ Monetization usage recorded:", data2);
    } catch (e) {
      console.warn("[ORBIS] ⚠️ monetization record failed:", e.message);
    }
  },

  addTestCredits(amount = 10) {
    this.state.credits += amount;
    this.saveState();
    this.updateUI();
    console.log(
      `[ORBIS] Test: ${amount} kredi eklendi. Toplam: ${this.state.credits}`
    );
  },

  simulateNewDay() {
    this.state.lastUsageDate = "2000-01-01";
    this.checkDailyReset();
    console.log("[ORBIS] Test: Yeni gün simüle edildi");
  },
};

// Global erişim
window.OrbisBridge = OrbisBridge;

// OrbisRewardedAds alias - results sayfası ve dashboard için uyumluluk
window.OrbisRewardedAds = {
  showForInterpretation: async function() {
    return OrbisBridge.showRewardedAd();
  },
  showForAnalysis: async function() {
    return OrbisBridge.showRewardedAd();
  },
};

// Sayfa yüklendiğinde başlat
document.addEventListener("DOMContentLoaded", async () => {
  await OrbisBridge.init();
  // Analytics: app_open (web PWA + mobile WebView)
  if (window.OrbisAnalytics) window.OrbisAnalytics.event('app_open', { platform: window.Capacitor?.isNativePlatform() ? 'native' : 'web' });
});
