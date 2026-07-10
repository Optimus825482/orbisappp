/**
 * ═══════════════════════════════════════════════════════════════════════════
 * ORBIS AI SUMMARY MODULE
 * Handles AI-generated cosmic summary loading and display
 * ═══════════════════════════════════════════════════════════════════════════
 */

async function loadAISummary() {
  const $content = $("#ai-summary-content");
  const $btn = $("#refresh-summary-btn");

  // Loading state - gizemli mesajlar
  const summaryLoadingMsgs = [
    "Doğum haritanızın matematiksel hesaplamaları tamamlandı, yapay zeka yorumunuz hazırlanıyor...",
    "Gezegenlerin konumları ve açıları ileri seviye AI modelleri tarafından analiz ediliyor...",
    "Kişisel karakter özellikleriniz Swiss Ephemeris verileriyle eşleştiriliyor...",
    "Yükselen burcunuz ve ev yerleşimleriniz yorumlanıyor, birazdan hazır...",
    "ORBIS'in uzman astroloji AI modeli size özel yorumunuzu oluşturuyor...",
  ];
  let _smi = 0;
  const _sme = document.createElement("p");
  $content.html(`
        <div class="flex flex-col items-center gap-2 py-3 text-center">
            <div class="w-8 h-8 rounded-full border-2 border-accent/30 border-t-accent animate-spin mb-1"></div>
            <p id="ai-summary-loading-msg-2" class="text-[10px] text-slate-400 font-medium leading-relaxed">${summaryLoadingMsgs[0]}</p>
        </div>
    `);
  // Her 2.5sn'de mesaj değiş
  const _stimer = setInterval(() => {
    _smi = (_smi + 1) % summaryLoadingMsgs.length;
    const el = document.getElementById("ai-summary-loading-msg-2");
    if (el) el.textContent = summaryLoadingMsgs[_smi];
  }, 2500);
  // Timer'ı global'a kaydet (cleanup için)
  window._summaryLoadingTimer = _stimer;
  $btn.prop("disabled", true).addClass("opacity-50");

  try {
    // Sadece birth_chart için gerekli verileri gönder
    const astroData = window.astroData || {};
    const BIRTH_CHART_KEYS = ["natal_planet_positions", "natal_houses", "natal_ascendant", "natal_aspects", "natal_additional_points"];
    const sendData = {};
    for (const key of BIRTH_CHART_KEYS) {
      if (astroData[key] !== undefined) sendData[key] = astroData[key];
    }
    const response = await fetch("/api/get_ai_interpretation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        interpretation_type: "birth_chart",
        astro_data: sendData,
        user_name: astroData.user_name || astroData.birth_info?.user_name || "Kullanıcı",
      }),
    });
    const result = await response.json();

    if (result.success) {
      clearInterval(window._summaryLoadingTimer);
      $content.html(marked.parse(result.interpretation));
      if (typeof CosmicLoader !== "undefined") {
        CosmicLoader.completeStep(1);
      }
    } else {
      $content.html(
        `<p class="text-red-400 text-[11px]">Özet yüklenemedi: ${result.error}</p>`
      );
      if (typeof CosmicLoader !== "undefined") {
        CosmicLoader.forceHide();
      }
    }
  } catch (error) {
    $content.html(
      `<p class="text-red-400 text-[11px]">Bağlantı hatası. Lütfen tekrar deneyin.</p>`
    );
    if (typeof CosmicLoader !== "undefined") {
      CosmicLoader.forceHide();
    }
  } finally {
    $btn.prop("disabled", false).removeClass("opacity-50");
  }
}

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = { loadAISummary };
}
