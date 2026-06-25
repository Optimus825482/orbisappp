/**
 * ORBIS Firebase Configuration
 * Auth + Firestore for user data sync
 */

const OrbisFirebase = {
  // Firebase Config
  config: {
    apiKey: "AIzaSyD9QYFaOQVxEvt3ENEfgaqVyweHuRy-MBQ",
    authDomain: "orbis-ffa9e.firebaseapp.com",
    projectId: "orbis-ffa9e",
    storageBucket: "orbis-ffa9e.firebasestorage.app",
    messagingSenderId: "768649602152",
    appId: "1:768649602152:web:d1cd9f7deadcdfef1907dd",
    measurementId: "G-V3FBQWDN61",
  },

  // State
  app: null,
  auth: null,
  db: null,
  user: null,
  userDoc: null,
  unsubscribe: null,

  // ═══════════════════════════════════════════════════════════════
  // BAŞLATMA
  // ═══════════════════════════════════════════════════════════════

  async init() {
    try {
      // Firebase SDK yüklü mü kontrol et
      if (typeof firebase === "undefined") {
        console.error("[Firebase] SDK yüklenmemiş!");
        return false;
      }

      // Firebase'i başlat
      this.app = firebase.initializeApp(this.config);
      this.auth = firebase.auth();
      this.db = firebase.firestore();

      console.log("[Firebase] Başlatıldı");

      // ═══════════════════════════════════════════════════════════════
      // CAPACITOR GOOGLE AUTH INITIALIZATION (Native Platform)
      // ═══════════════════════════════════════════════════════════════
      await this.initCapacitorGoogleAuth();

      // Redirect sonrası result kontrolü (Web için)
      try {
        const result = await this.auth.getRedirectResult();
        if (result.user) {
          console.log("[Firebase] Redirect giriş başarılı:", result.user.email);
        }
      } catch (redirectError) {
        console.log(
          "[Firebase] Redirect result yok veya hata:",
          redirectError.code
        );
      }

      // Auth state listener
      this.auth.onAuthStateChanged((user) => {
        this.handleAuthStateChange(user);
      });

      return true;
    } catch (error) {
      console.error("[Firebase] Başlatma hatası:", error);
      return false;
    }
  },

  // Capacitor GoogleAuth Plugin Initialize
  async initCapacitorGoogleAuth() {
    try {
      const isNative =
        typeof Capacitor !== "undefined" && Capacitor.isNativePlatform();

      if (!isNative) {
        console.log("[GoogleAuth] Web platform - skip native init");
        return;
      }

      console.log("[GoogleAuth] Native platform detected - initializing...");

      // Plugin'i bul
      let GoogleAuth = null;

      if (Capacitor.Plugins && Capacitor.Plugins.GoogleAuth) {
        GoogleAuth = Capacitor.Plugins.GoogleAuth;
      } else if (window.Plugins && window.Plugins.GoogleAuth) {
        GoogleAuth = window.Plugins.GoogleAuth;
      }

      if (!GoogleAuth) {
        console.warn("[GoogleAuth] Plugin bulunamadı - sonra tekrar denenecek");
        return;
      }

      // Plugin'i initialize et
      await GoogleAuth.initialize({
        clientId:
          "768649602152-aous93aj0cnn8bjdsqvjo4t62ip2feci.apps.googleusercontent.com",
        scopes: ["profile", "email"],
        grantOfflineAccess: true,
      });

      console.log("[GoogleAuth] Plugin başarıyla initialize edildi!");
    } catch (error) {
      console.error("[GoogleAuth] Initialize hatası:", error);
      // Hatayı yutuyoruz çünkü bazı durumlarda (Android'de zaten init edilmişse) hata verebilir
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // AUTH
  // ═══════════════════════════════════════════════════════════════

  async signInWithGoogle() {
    try {
      // Native platform kontrolü (Capacitor Android/iOS)
      const isNative =
        typeof Capacitor !== "undefined" && Capacitor.isNativePlatform();

      console.log("[Firebase] isNative:", isNative);

      if (isNative) {
        console.log(
          "[Firebase] Native platform - Capacitor Google Auth deneniyor..."
        );

        // Capacitor Google Auth plugin kontrolü
        let GoogleAuth = null;

        // Yeni Capacitor 5+ API
        if (
          typeof Capacitor !== "undefined" &&
          Capacitor.Plugins &&
          Capacitor.Plugins.GoogleAuth
        ) {
          GoogleAuth = Capacitor.Plugins.GoogleAuth;
        }

        // Alternatif: Global @codetrix-studio/capacitor-google-auth
        if (!GoogleAuth && window.Plugins && window.Plugins.GoogleAuth) {
          GoogleAuth = window.Plugins.GoogleAuth;
        }

        if (!GoogleAuth) {
          console.error("[Firebase] GoogleAuth plugin bulunamadı - Browser OAuth fallback deneniyor");
          return await this._signInWithBrowserOAuth();
        }

        try {
          console.log("[Firebase] GoogleAuth.signIn() çağrılıyor...");

          // Native Google Sign-In
          const googleUser = await GoogleAuth.signIn();

          console.log(
            "[Firebase] Native Google Sign-In başarılı:",
            googleUser.email
          );
          console.log(
            "[Firebase] idToken mevcut:",
            !!googleUser.authentication?.idToken
          );

          if (!googleUser.authentication?.idToken) {
            throw new Error("idToken alınamadı!");
          }

          // Firebase credential oluştur
          const credential = firebase.auth.GoogleAuthProvider.credential(
            googleUser.authentication.idToken
          );

          // Firebase'e giriş yap
          const result = await this.auth.signInWithCredential(credential);
          console.log("[Firebase] Firebase giriş başarılı:", result.user.email);
          if (window.OrbisAnalytics) window.OrbisAnalytics.event('login', { method: 'google' });

          return result.user;
        } catch (nativeError) {
          console.error("[Firebase] Native Google Auth hatası:", nativeError);

          // Kullanıcı iptal etti mi?
          const errorMsg = (nativeError && (nativeError.message || nativeError.errorMessage)) || JSON.stringify(nativeError);

          if (
            errorMsg.includes("canceled") ||
            errorMsg.includes("cancelled") ||
            errorMsg.includes("12501") ||
            errorMsg.includes("user_cancelled") ||
            nativeError?.code === "12501"
          ) {
            console.log("[Firebase] Kullanıcı giriş işlemini iptal etti");
            return null;
          }

          // ⚠️ KRİTİK: Native Google Auth başarısız oldu (Play Services / SHA-1 / config sorunu)
          // Browser OAuth flow'a fallback yap — her durumda çalışır
          console.warn("[Firebase] Native Google Auth basarisiz, Browser OAuth fallback deneniyor:", errorMsg);
          return await this._signInWithBrowserOAuth();
        }
      }

      // ═══════════════════════════════════════════════════════════════
      // WEB PLATFORM - Normal tarayıcı için
      // ═══════════════════════════════════════════════════════════════

      const provider = new firebase.auth.GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });

      try {
        const result = await this.auth.signInWithPopup(provider);
        console.log("[Firebase] Google ile giriş başarılı:", result.user.email);
        if (window.OrbisAnalytics) {
          const isNew = result.additionalUserInfo?.isNewUser;
          window.OrbisAnalytics.event(isNew ? 'sign_up' : 'login', { method: 'google' });
        }
        return result.user;
      } catch (popupError) {
        console.error(
          "[Firebase] Popup hatası:",
          popupError.code,
          popupError.message
        );

        if (
          popupError.code === "auth/popup-blocked" ||
          popupError.code === "auth/popup-closed-by-user"
        ) {
          console.log("[Firebase] Popup başarısız, redirect deneniyor...");
          await this.auth.signInWithRedirect(provider);
          return null;
        }
        throw popupError;
      }
    } catch (error) {
      console.error("[Firebase] Google giriş hatası:", error);
      alert("Giriş sırasında beklenmeyen bir hata oluştu: " + error.message);
      return null;
    }
  },

  /**
   * Browser-based OAuth fallback — Capacitor Browser plugin ile.
   * Native Google Auth başarısız olduğunda (Play Services eksik, SHA-1 uyumsuz, vs.)
   * sistem tarayıcısında OAuth flow'u açarak giriş yapılmasını sağlar.
   */
  async _signInWithBrowserOAuth() {
    try {
      const isNative =
        typeof Capacitor !== "undefined" && Capacitor.isNativePlatform();

      if (!isNative) {
        // Web'de zaten popup deneniyor, bu fallback Web için değil
        return null;
      }

      console.log("[Firebase] Browser OAuth fallback başlatılıyor...");

      // Capacitor Browser plugin kontrolü
      const Browser = (Capacitor.Plugins && Capacitor.Plugins.Browser) ||
                       (window.Plugins && window.Plugins.Browser);

      if (!Browser) {
        console.error("[Firebase] Browser plugin yok - Capacitor Browser kurulu olmali");
        alert(
          "Google giris simdi musait degil.\n\n" +
          "Lutfen uygulamayi kapatip Google Play Store'dan guncellestirmisini deneyin."
        );
        return null;
      }

      // Provider ayarla
      const provider = new firebase.auth.GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });

      // signInWithRedirect akışı: Capacitor Browser OAuth callback'i yakalar
      // ve uygulamaya geri doner
      await this.auth.signInWithRedirect(provider);
      console.log("[Firebase] Browser OAuth redirect başlatıldı");
      return null; // Redirect sonrası getRedirectResult() ile user handle edilecek

    } catch (e) {
      console.error("[Firebase] Browser OAuth fallback hatası:", e);
      alert("Giris sirasinda hata: " + e.message);
      return null;
    }
  },

  async signOut() {
    try {
      // Firestore listener'ı kaldır
      if (this.unsubscribe) {
        this.unsubscribe();
        this.unsubscribe = null;
      }

      // Heartbeat'i durdur
      this.stopHeartbeat();

      await this.auth.signOut();
      this.user = null;
      this.userDoc = null;

      console.log("[Firebase] Çıkış yapıldı");

      // UI güncelle
      this.updateAuthUI();

      // OrbisBridge'i sıfırla
      if (window.OrbisBridge) {
        window.OrbisBridge.resetToLocal();
      }

      return true;
    } catch (error) {
      console.error("[Firebase] Çıkış hatası:", error);
      return false;
    }
  },

  handleAuthStateChange(user) {
    this.user = user;

    if (user) {
      console.log("[Firebase] Kullanıcı giriş yaptı:", user.email);
      this.loadUserData();

      // Son login kaydı
      fetch("/api/stats/user-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email, display_name: user.displayName || user.email }),
      }).catch(() => {});

      // Heartbeat başlat (her 60sn)
      this.startHeartbeat(user.email, user.displayName);

      // GA: Login event
      if (typeof gtag === "function") {
        gtag("event", "login", {
          method: "Google",
          user_id: user.uid,
        });
        console.log("[GA] Login event sent");
      }

      // Mobile app'e kullanıcı bilgisini gönder (reklam kontrolü için)
      if (
        window.OrbisApp &&
        typeof window.OrbisApp.onUserLogin === "function"
      ) {
        window.OrbisApp.onUserLogin(user);
      }
    } else {
      console.log("[Firebase] Kullanıcı çıkış yaptı");
      this.userDoc = null;

      // GA: Logout event
      if (typeof gtag === "function") {
        gtag("event", "logout");
        console.log("[GA] Logout event sent");
      }

      // Mobile app'e çıkış bilgisini gönder
      if (
        window.OrbisApp &&
        typeof window.OrbisApp.onUserLogout === "function"
      ) {
        window.OrbisApp.onUserLogout();
      }
    }

    this.updateAuthUI();
  },

  // ═══════════════════════════════════════════════════════════════
  // FIRESTORE - KULLANICI VERİLERİ
  // ═══════════════════════════════════════════════════════════════

  async loadUserData() {
    if (!this.user) return null;

    try {
      const docRef = this.db.collection("users").doc(this.user.uid);

      // Realtime listener
      this.unsubscribe = docRef.onSnapshot((doc) => {
        if (doc.exists) {
          this.userDoc = doc.data();
          console.log("[Firebase] Kullanıcı verisi yüklendi:", this.userDoc);
        } else {
          // Yeni kullanıcı - varsayılan veri oluştur
          this.createNewUser();
        }

        // OrbisBridge'e sync et
        this.syncToOrbisBridge();
      });

      return this.userDoc;
    } catch (error) {
      console.error("[Firebase] Veri yükleme hatası:", error);
      return null;
    }
  },

  async createNewUser() {
    if (!this.user) return;

    const newUserData = {
      email: this.user.email,
      displayName: this.user.displayName,
      photoURL: this.user.photoURL,
      createdAt: firebase.firestore.FieldValue.serverTimestamp(),

      // Monetizasyon
      isPremium: false,
      premiumPackageId: null,
      premiumExpiry: null,
      credits: 0,

      // Kullanım istatistikleri
      totalAnalyses: 0,
      installDate: new Date().toISOString().split("T")[0],

      // Günlük kullanım (her gün sıfırlanır)
      dailyUsage: {
        date: new Date().toISOString().split("T")[0],
        count: 0,
        adsWatched: 0,
      },
    };

    try {
      await this.db.collection("users").doc(this.user.uid).set(newUserData);
      this.userDoc = newUserData;
      console.log("[Firebase] Yeni kullanıcı oluşturuldu");

      // Stats counter güncelle
      try {
        await fetch("/api/stats/user-created", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_premium: false })
        });
      } catch (e) {
        console.log("[Stats] user-created notification failed", e);
      }
    } catch (error) {
      console.error("[Firebase] Kullanıcı oluşturma hatası:", error);
    }
  },

  async updateUserData(updates) {
    if (!this.user) return false;

    try {
      await this.db
        .collection("users")
        .doc(this.user.uid)
        .update({
          ...updates,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
        });
      console.log("[Firebase] Kullanıcı verisi güncellendi");
      return true;
    } catch (error) {
      console.error("[Firebase] Güncelleme hatası:", error);
      return false;
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // PREMIUM & KREDİ İŞLEMLERİ
  // ═══════════════════════════════════════════════════════════════

  async activatePremium(packageId, credits, months) {
    // DEPRECATED: Premium durumu artık client Firestore write ile atanmaz.
    // Backend verify-purchase route + Admin SDK tek kaynak (firestore.rules).
    // Bu metod saklı tutuldu (eski referanslar) ama no-op + uyarı.
    console.warn("[ORBIS] activatePremium client-side deprecate. Backend '/api/monetization/verify-purchase' kullanın.");
    return false;
  },

  async addCredits(amount, packagePrice) {
    if (!this.user) return false;

    const success = await this.updateUserData({
      credits: firebase.firestore.FieldValue.increment(amount),
    });

    if (success) {
      await this.logPurchase("credits", amount, packagePrice);
    }

    return success;
  },

  async useCredit() {
    if (!this.user || !this.userDoc) return false;
    if (this.userDoc.credits <= 0) return false;

    return await this.updateUserData({
      credits: firebase.firestore.FieldValue.increment(-1),
      totalAnalyses: firebase.firestore.FieldValue.increment(1),
    });
  },

  async updateDailyUsage() {
    if (!this.user) return;

    const today = new Date().toISOString().split("T")[0];

    // Günlük reset kontrolü
    if (this.userDoc?.dailyUsage?.date !== today) {
      await this.updateUserData({
        "dailyUsage.date": today,
        "dailyUsage.count": 1,
        "dailyUsage.adsWatched": 0,
      });
    } else {
      await this.updateUserData({
        "dailyUsage.count": firebase.firestore.FieldValue.increment(1),
      });
    }
  },

  async logPurchase(type, item, amount) {
    if (!this.user) return;

    try {
      await this.db.collection("purchases").add({
        userId: this.user.uid,
        type: type,
        item: item,
        amount: amount,
        timestamp: firebase.firestore.FieldValue.serverTimestamp(),
      });
    } catch (error) {
      console.error("[Firebase] Satın alma kaydı hatası:", error);
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // SYNC
  // ═══════════════════════════════════════════════════════════════

  syncToOrbisBridge() {
    if (!window.OrbisBridge || !this.userDoc) return;

    // Firebase verilerini OrbisBridge'e aktar
    window.OrbisBridge.state.isPremium = this.userDoc.isPremium || false;
    window.OrbisBridge.state.credits = this.userDoc.credits || 0;
    window.OrbisBridge.state.premiumPackageId = this.userDoc.premiumPackageId;
    window.OrbisBridge.state.premiumExpiry = this.userDoc.premiumExpiry;
    window.OrbisBridge.state.totalAnalyses = this.userDoc.totalAnalyses || 0;

    // Günlük kullanım
    const today = new Date().toISOString().split("T")[0];
    if (this.userDoc.dailyUsage?.date === today) {
      window.OrbisBridge.state.todayUsage = this.userDoc.dailyUsage.count || 0;
      window.OrbisBridge.state.todayAdsWatched =
        this.userDoc.dailyUsage.adsWatched || 0;
    } else {
      window.OrbisBridge.state.todayUsage = 0;
      window.OrbisBridge.state.todayAdsWatched = 0;
    }

    window.OrbisBridge.updateUI();
    console.log("[Firebase] OrbisBridge sync tamamlandı");
  },

  // ═══════════════════════════════════════════════════════════════
  // UI
  // ═══════════════════════════════════════════════════════════════

  updateAuthUI() {
    const loginBtn = document.getElementById("login-btn");
    const userInfo = document.getElementById("user-info");
    const userAvatar = document.getElementById("user-avatar");
    const userName = document.getElementById("user-name");

    // Mobile elements
    const mobileProfileIcon = document.getElementById("mobile-profile-icon");
    const mobileAvatar = document.getElementById("mobile-avatar");

    if (this.user) {
      // Giriş yapılmış - Desktop
      if (loginBtn) loginBtn.style.display = "none";
      if (userInfo) {
        userInfo.style.display = "flex";
        userInfo.classList.remove("hidden");
      }
      if (userAvatar) userAvatar.src = this.user.photoURL || "";
      if (userName)
        userName.textContent = this.user.displayName || this.user.email;

      // Mobile
      if (mobileProfileIcon) mobileProfileIcon.classList.add("hidden");
      if (mobileAvatar) {
        mobileAvatar.src = this.user.photoURL || "";
        mobileAvatar.classList.remove("hidden");
      }
    } else {
      // Giriş yapılmamış - Desktop
      if (loginBtn) loginBtn.style.display = "flex";
      if (userInfo) {
        userInfo.style.display = "none";
        userInfo.classList.add("hidden");
      }

      // Mobile
      if (mobileProfileIcon) mobileProfileIcon.classList.remove("hidden");
      if (mobileAvatar) mobileAvatar.classList.add("hidden");
    }

    // Mobile auth modal güncelle (varsa)
    if (typeof updateMobileAuthView === "function") {
      updateMobileAuthView();
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════

  isLoggedIn() {
    return !!this.user;
  },

  getCurrentUser() {
    return this.user;
  },

  getUserData() {
    return this.userDoc;
  },

  // ═══════════════════════════════════════════════════════════════
  // HESAP SİLME (GDPR/KVKK)
  // ═══════════════════════════════════════════════════════════════

  async deleteAccount() {
    if (!this.user) {
      throw new Error("Hesap silmek için giriş yapmalısınız.");
    }

    const userId = this.user.uid;
    console.log("[Firebase] Hesap silme başlatılıyor:", userId);

    try {
      // 1. Firestore listener'ı kaldır
      if (this.unsubscribe) {
        this.unsubscribe();
        this.unsubscribe = null;
      }

      // 2. Firestore'dan kullanıcı verisini sil
      if (this.db) {
        // Ana kullanıcı dokümanı
        await this.db.collection("users").doc(userId).delete();
        console.log("[Firebase] Kullanıcı verisi silindi");

        // Satın alma geçmişi (varsa)
        const purchasesSnapshot = await this.db
          .collection("purchases")
          .where("userId", "==", userId)
          .get();

        const batch = this.db.batch();
        purchasesSnapshot.forEach((doc) => {
          batch.delete(doc.ref);
        });
        await batch.commit();
        console.log("[Firebase] Satın alma geçmişi silindi");
      }

      // 3. GA: Hesap silme event'i
      if (typeof gtag === "function") {
        gtag("event", "account_deleted", {
          user_id: userId,
        });
      }

      // 4. Local storage temizle
      localStorage.removeItem("orbis_state");
      localStorage.removeItem("orbis_user");
      localStorage.removeItem("tts-speed");

      // 5. State sıfırla
      this.user = null;
      this.userDoc = null;

      // 6. Firebase Auth'dan çıkış yap
      await this.auth.signOut();

      console.log("[Firebase] Hesap başarıyla silindi");

      // 7. OrbisBridge'i sıfırla
      if (window.OrbisBridge) {
        window.OrbisBridge.resetToLocal();
      }

      return { success: true, message: "Hesabınız başarıyla silindi." };
    } catch (error) {
      console.error("[Firebase] Hesap silme hatası:", error);
      throw error;
    }
  },

  // ═══════════════════════════════════════════════════════════════
  // PUSH NOTIFICATIONS (FCM)
  // ═══════════════════════════════════════════════════════════════

  messaging: null,
  fcmToken: null,

  async initMessaging() {
    try {
      // Service Worker kontrolü
      if (!("serviceWorker" in navigator)) {
        console.log("[FCM] Service Worker desteklenmiyor");
        return false;
      }

      // Notification izni kontrolü
      if (!("Notification" in window)) {
        console.log("[FCM] Notification API desteklenmiyor");
        return false;
      }

      // Firebase Messaging Service Worker'ı register et
      const registration = await navigator.serviceWorker.register(
        "/firebase-messaging-sw.js",
        {
          scope: "/firebase-cloud-messaging-push-scope",
        }
      );

      // Service Worker'ın aktif olmasını bekle
      await navigator.serviceWorker.ready;
      console.log("[FCM] Service Worker registered:", registration.scope);

      this.messaging = firebase.messaging();

      // Foreground mesaj dinleyicisi
      this.messaging.onMessage((payload) => {
        console.log("[FCM] Foreground mesaj:", payload);
        this.showNotification(payload);
      });

      console.log("[FCM] Messaging başlatıldı");
      return true;
    } catch (error) {
      console.error("[FCM] Messaging başlatma hatası:", error);
      return false;
    }
  },

  async requestNotificationPermission() {
    try {
      const permission = await Notification.requestPermission();

      if (permission === "granted") {
        console.log("[FCM] Bildirim izni verildi");
        return await this.getFCMToken();
      } else {
        console.log("[FCM] Bildirim izni reddedildi");
        return null;
      }
    } catch (error) {
      console.error("[FCM] İzin hatası:", error);
      return null;
    }
  },

  async getFCMToken() {
    if (!this.messaging) {
      await this.initMessaging();
    }

    try {
      // VAPID key - Firebase Console > Project Settings > Cloud Messaging > Web Push certificates
      const vapidKey =
        "BDG800ijmQ1av11kHWR-ZnW_gVUKUYjKMH7oYqKnF-BsSb2K4ECB9PL0cQzpP90jehx5zwnR7WH46kYdlq6kUbE";

      const token = await this.messaging.getToken({ vapidKey });

      if (token) {
        this.fcmToken = token;
        console.log("[FCM] Token alındı:", token.slice(0, 20) + "...");

        // Token'ı backend'e kaydet
        await this.saveFCMToken(token);

        return token;
      }
    } catch (error) {
      console.error("[FCM] Token alma hatası:", error);
    }

    return null;
  },

  async saveFCMToken(token) {
    if (!this.user) return false;

    try {
      // Backend'e kaydet
      const response = await fetch("/api/push/register-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId: this.user.uid,
          token: token,
          platform: this.detectPlatform(),
        }),
      });

      const result = await response.json();
      console.log("[FCM] Token kaydedildi:", result);
      return result.success;
    } catch (error) {
      console.error("[FCM] Token kaydetme hatası:", error);
      return false;
    }
  },

  async subscribeToTopic(topic) {
    if (!this.fcmToken) return false;

    try {
      const response = await fetch("/api/push/subscribe-topic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: this.fcmToken,
          topic: topic,
        }),
      });

      const result = await response.json();
      return result.success;
    } catch (error) {
      console.error("[FCM] Topic subscribe hatası:", error);
      return false;
    }
  },

  showNotification(payload) {
    // Foreground'da bildirim göster
    const { title, body, icon } = payload.notification || {};
    const data = payload.data || {};

    // Custom notification UI
    if (typeof showToast === "function") {
      showToast(title, body);
    } else {
      // Fallback: Browser notification
      if (Notification.permission === "granted") {
        new Notification(title, {
          body: body,
          icon:
            icon || "/static/all-icons/Android/mipmap-xxxhdpi/ic_launcher.png",
          data: data,
        });
      }
    }
  },

  detectPlatform() {
    const ua = navigator.userAgent;
    if (/android/i.test(ua)) return "android";
    if (/iPad|iPhone|iPod/.test(ua)) return "ios";
    return "web";
  },

  // Heartbeat - her 60 saniyede bir backend'e canlı olduğunu bildir
  _heartbeatInterval: null,

  startHeartbeat(email, displayName) {
    // Önceki intervali temizle
    if (this._heartbeatInterval) {
      clearInterval(this._heartbeatInterval);
    }

    // İlk heartbeat'i hemen gönder
    this._sendHeartbeat(email, displayName);

    // Sonra her 5 dakikada bir — backend load azalt (60s → 300s).
    // 60 aktif user = 86k req/gün → 300s = ~17k req/gün.
    this._heartbeatInterval = setInterval(() => {
      this._sendHeartbeat(email, displayName);
    }, 300000);
  },

  async _sendHeartbeat(email, displayName) {
    try {
      await fetch("/api/stats/heartbeat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, display_name: displayName }),
      });
    } catch (e) {
      // Sessizce başarısız ol - önemli değil
    }
  },

  stopHeartbeat() {
    if (this._heartbeatInterval) {
      clearInterval(this._heartbeatInterval);
      this._heartbeatInterval = null;
    }
  },
};

// Global erişim
window.OrbisFirebase = OrbisFirebase;
