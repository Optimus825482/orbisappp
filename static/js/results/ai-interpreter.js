/**
 * ═══════════════════════════════════════════════════════════════════════════
 * ORBIS AI INTERPRETER
 * Handles AI interpretation requests and modal display
 * ═══════════════════════════════════════════════════════════════════════════
 */

// Global state
window.currentInterpretationText = "";

const interpretationTitles = {
  birth_chart: "Doğum Haritası Analizi",
  relationship: "İlişki Analizi",
  psychological_karmic: "Psikolojik & Karmik Analiz",
  daily: "Günlük Yorum",
  transits: "Transit Analizi",
  short_term: "Kısa Vadeli Öngörü",
  long_term: "Uzun Vadeli Öngörü",
  career: "Kariyer Analizi",
  health: "Sağlık Analizi",
  finance: "Finansal Analiz",
  spiritual: "Ruhsal Gelişim",
  summary: "Kozmik Özet",
};

async function interpretTab(type) {
  openAIModal();
  const $body = $("#ai-modal-body");
  const $title = $("#ai-modal-title");

  $title.text(interpretationTitles[type] || "AI Analizi");

  // Dinamik geri sayım sayacı
  const startTime = Date.now();
  $body.html(`
        <div class="flex flex-col items-center justify-center py-10 gap-4">
            <div class="relative w-20 h-20">
                <svg class="w-20 h-20 -rotate-90" viewBox="0 0 80 80">
                    <circle class="text-slate-700/40" stroke="currentColor" stroke-width="4" fill="none" cx="40" cy="40" r="34"/>
                    <circle id="ai-progress-ring" class="text-primary" stroke="currentColor" stroke-width="4" fill="none" cx="40" cy="40" r="34"
                        stroke-dasharray="213.6" stroke-dashoffset="213.6" stroke-linecap="round"/>
                </svg>
                <div class="absolute inset-0 flex items-center justify-center">
                    <span id="ai-elapsed" class="text-lg font-bold text-slate-300">0sn</span>
                </div>
            </div>
            <p id="ai-status-text" class="text-sm text-slate-400 text-center max-w-xs leading-relaxed">Doğum haritanız hazırlanıyor...</p>
            <p id="ai-disclaimer" class="text-[10px] text-slate-600 text-center max-w-xs mt-2 hidden">
                ⚠️ Bu yorumlar yapay zeka tarafından, ileri seviye matematiksel astroloji hesaplamalarına dayanarak oluşturulmuştur. Eğlence amaçlıdır, yatırım veya yaşamsal karar tavsiyesi niteliği taşımaz. Nihai karar her zaman size aittir.
            </p>
        </div>
    `);

  // Dinamik dönen mesajlar - gizemli, bilgilendirici, eğlenceli
  const cycleMessages = [
    // 0-5sn: Hesaplama aşaması
    "🪐 Doğum haritanızın matematiksel hesaplamaları yapılıyor...",
    "⭐ Gezegenlerin konumları Swiss Ephemeris ile hesaplanıyor...",
    "🌙 Ay düğümleri ve tutulma verileri çözümleniyor...",
    "🔄 139 farklı gezegen açısı değerlendiriliyor...",
    "📐 Ev girişleri ve ascendant hesaplanıyor...",
    // 5-10sn: Vedic + derin analiz
    "🕉️ Vedik astroloji hesaplamaları (Navamsa) yapılıyor...",
    "📿 Vimshottari Dasha dönemleri sıralanıyor...",
    "✨ Sabit yıldızların (44 adet) etkileri ölçülüyor...",
    "🔮 Arap noktaları ve Şans Noktası konumlandırılıyor...",
    "🌌 Derin harmonik analiz (H5-H12) işleniyor...",
    // 10-18sn: AI yorumlama
    "🧠 İleri seviye yapay zeka modelleri verileri yorumluyor...",
    "🤖 AI astrolojik pattern'leri tanımlıyor...",
    "📊 Gezegen yerleşimleri yaşam alanlarına göre sınıflandırılıyor...",
    "💫 Transit etkileri natal haritanızla karşılaştırılıyor...",
    "🎯 Kişisel yaşam temalarınız belirleniyor...",
    // 18-28sn: Sentez
    "🧩 Tüm astrolojik göstergeler birleştiriliyor...",
    "📝 Kapsamlı yorum metni oluşturuluyor...",
    "🔍 Kariyer, ilişki, sağlık ve finans başlıkları hazırlanıyor...",
    "💎 Spiritüel ve karmik içgörüler ekleniyor...",
    "🌟 Size özel tavsiyeler formüle ediliyor...",
    // 28+sn: Son rötuş
    "⚡ Son rötuşlar yapılıyor, az kaldı...",
    "🌠 Kozmik mesajınız neredeyse hazır...",
    "🎭 Astroloji bir rehberdir, nihai karar her zaman size aittir...",
    "📖 Yıldızlar eğilimleri gösterir, kaderi değil...",
    "✨ Bu yorumlar eğlence amaçlıdır, sezgilerinize güvenin...",
  ];

  const disclaimerEl = document.getElementById("ai-disclaimer");
  const elapsedEl = document.getElementById("ai-elapsed");
  const statusEl = document.getElementById("ai-status-text");
  const ringEl = document.getElementById("ai-progress-ring");
  let lastIdx = -1;

  const tick = setInterval(() => {
    const sec = Math.round((Date.now() - startTime) / 1000);
    if (elapsedEl) elapsedEl.textContent = sec + "sn";

    // Progress ring: 60sn'de tamamlansın
    if (ringEl) {
      const progress = Math.min(sec / 60, 1);
      ringEl.style.strokeDashoffset = 213.6 * (1 - progress);
    }

    // Mesaj döngüsü: her 2-3 saniyede bir değiş
    const msgIdx = Math.floor(sec / 2.5) % cycleMessages.length;
    if (msgIdx !== lastIdx && statusEl) {
      statusEl.textContent = cycleMessages[msgIdx];
      lastIdx = msgIdx;
    }

    // 12sn sonra disclaimer göster
    if (sec >= 12 && disclaimerEl && disclaimerEl.classList.contains("hidden")) {
      disclaimerEl.classList.remove("hidden");
    }
  }, 1000);

  try {
    const astroData = window.astroData || {};
    const response = await fetch("/api/get_ai_interpretation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        interpretation_type: type,
        astro_data: astroData,
        user_name: astroData.user_name || astroData.birth_info?.user_name || "Kullanıcı",
      }),
    });

    clearInterval(tick);
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    const result = await response.json();

    if (result.success) {
      window.currentInterpretationText = result.interpretation;
      $body.html(`
                <div class="text-[10px] text-slate-500 mb-2">✨ ${elapsed} saniyede hazırlandı</div>
                ${marked.parse(result.interpretation)}
            `);
    } else {
      $body.html(`
                <div class="text-center py-8">
                    <span class="material-icons-round text-4xl text-red-400 mb-4">error_outline</span>
                    <p class="text-red-400">${result.error || "Bir hata oluştu"}</p>
                    <p class="text-xs text-slate-500 mt-2">${elapsed} saniye sonra başarısız</p>
                </div>
            `);
    }
  } catch (error) {
    clearInterval(tick);
    console.error("Interpretation error:", error);
    $body.html(`
            <div class="text-center py-8">
                <span class="material-icons-round text-4xl text-red-400 mb-4">wifi_off</span>
                <p class="text-red-400">Bağlantı hatası. Lütfen tekrar deneyin.</p>
            </div>
        `);
  }
}

function openAIModal() {
  const modal = document.getElementById("ai-modal");
  if (modal) {
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }
}

function closeAIModal() {
  const modal = document.getElementById("ai-modal");
  if (modal) {
    modal.classList.add("hidden");
    document.body.style.overflow = "";
  }
  // TTS'i durdur
  if (typeof TTS !== "undefined" && TTS.status !== "idle") {
    TTS.stop();
  }
}

function formatInterpretation(text) {
  if (!text) return "";
  let formatted = text
    .replace(
      /\*\*(.*?)\*\*/g,
      '<strong class="text-white font-semibold">$1</strong>'
    )
    .replace(/\n\n/g, '</p><p class="mb-4">')
    .replace(
      /### (.*)/g,
      '<h3 class="text-lg font-bold text-white mt-6 mb-3">$1</h3>'
    )
    .replace(
      /## (.*)/g,
      '<h2 class="text-xl font-bold text-white mt-8 mb-4">$1</h2>'
    )
    .replace(
      /- (.*)/g,
      '<li class="ml-4 mb-2 flex items-start gap-2"><span class="text-primary mt-1">•</span> $1</li>'
    );
  return `<p class="mb-4">${formatted}</p>`;
}

// Export
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    interpretTab,
    openAIModal,
    closeAIModal,
    formatInterpretation,
  };
}
