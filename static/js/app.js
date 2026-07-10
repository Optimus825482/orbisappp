var searchTimeout;

async function searchLocation(query, type = "birth") {
  if (!query || query.length < 3) {
    const resultsDiv = document.getElementById(
      type === "birth" ? "locationResults" : "transit_location_suggestions"
    );
    resultsDiv.innerHTML = "";
    resultsDiv.style.display = "none";
    return;
  }

  try {
    const response = await fetch(
      `/search_location?query=${encodeURIComponent(query)}`
    );
    const data = await response.json();

    const resultsDiv = document.getElementById(
      type === "birth" ? "locationResults" : "transit_location_suggestions"
    );
    resultsDiv.innerHTML = "";

    if (data.locations && data.locations.length > 0) {
      data.locations.forEach((location) => {
        const locationDiv = document.createElement("div");
        locationDiv.className = "location-item";
        locationDiv.textContent = `${location.name}, ${location.country}`;
        locationDiv.dataset.lat = location.lat;
        locationDiv.dataset.lon = location.lon;
        locationDiv.onclick = () => selectLocation(location, type);
        resultsDiv.appendChild(locationDiv);
      });
      resultsDiv.style.display = "block";
    } else {
      resultsDiv.innerHTML = '<div class="no-results">Sonuç bulunamadı</div>';
      resultsDiv.style.display = "block";
    }
  } catch (error) {
    console.error("Konum arama hatası:", error);
  }
}

function selectLocation(location, type = "birth") {
  if (type === "birth") {
    document.getElementById(
      "birth_place"
    ).value = `${location.name}, ${location.country}`;
    document.getElementById("birth_latitude").value = location.lat;
    document.getElementById("birth_longitude").value = location.lon;
    document.getElementById("locationResults").style.display = "none";
  } else {
    document.getElementById(
      "transit_location_search"
    ).value = `${location.name}, ${location.country}`;
    document.getElementById("transit_latitude").value = location.lat;
    document.getElementById("transit_longitude").value = location.lon;
    document.getElementById("transit_location_suggestions").style.display =
      "none";
  }
}

// Ana form gönderim fonksiyonu
async function submitAstroForm(event) {
  event.preventDefault();

  // Loading durumunu göster
  document.getElementById("loading").style.display = "flex";
  document.getElementById("form-container").style.display = "none";

  try {
    // Form verilerini topla
    const formData = {
      name: document.getElementById("name").value || "Değerli Danışanım",
      birth_date: document.getElementById("birth_date").value,
      birth_time: document.getElementById("birth_time").value,
      birth_latitude: document.getElementById("birth_latitude").value,
      birth_longitude: document.getElementById("birth_longitude").value,
      birth_place: document.getElementById("birth_place")?.value || "",
      house_system: document.getElementById("house_system").value || "P",
    };

    // Transit bilgilerini ekle (eğer varsa)
    const transitDate = document.getElementById("transit_date")?.value;
    const transitTime = document.getElementById("transit_time")?.value;
    const transitLatitude = document.getElementById("transit_latitude")?.value;
    const transitLongitude =
      document.getElementById("transit_longitude")?.value;

    if (transitDate) formData.transit_date = transitDate;
    if (transitTime) formData.transit_time = transitTime;
    if (transitLatitude) formData.transit_latitude = transitLatitude;
    if (transitLongitude) formData.transit_longitude = transitLongitude;

    console.log("Gönderilen form verileri:", formData);

    // API isteği yap
    const response = await fetch("/calculate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(formData),
    });

    // API yanıtını kontrol et
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Hesaplama sırasında bir hata oluştu");
    }

    const result = await response.json();
    console.log("API yanıtı:", result);

    if (result.success) {
      try {
        // Astro verisini localStorage'a kaydet
        const astroDataStr = JSON.stringify(result.astro_data);
        localStorage.setItem("astro_data", astroDataStr);
        localStorage.setItem("user_name", result.user_name || formData.name);

        console.log(`LocalStorage'a kaydedildi:`, {
          astro_data_size: astroDataStr.length,
          user_name: result.user_name || formData.name,
        });

        // LocalStorage'a veri kaydedildikten sonra sonuçlar sayfasına yönlendir
        window.location.href = "/results";
      } catch (localStorageError) {
        console.error("LocalStorage kayıt hatası:", localStorageError);
        alert(
          "Veriler tarayıcınıza kaydedilemedi. Yine de sonuçlar gösterilecektir."
        );
        // LocalStorage hatası olsa bile sonuçları görebilmesi için yönlendir
        window.location.href = "/results";
      }
    } else {
      throw new Error(result.error || "Bilinmeyen bir hata oluştu");
    }
  } catch (error) {
    console.error("Form gönderimi hatası:", error);

    // Hatayı göster
    document.getElementById("loading").style.display = "none";
    document.getElementById("form-container").style.display = "block";

    const errorDiv = document.getElementById("error-message");
    if (errorDiv) {
      errorDiv.textContent = `Hata: ${error.message}`;
      errorDiv.style.display = "block";
    } else {
      alert(`Hata: ${error.message}`);
    }
  }
}

// Namespace oluştur
window.astro = {
  currentInterpretationType: "",
  currentSessionId: "",
  lastInterpretation: "",
  currentUtterance: null,

  closeModal() {
    document.getElementById("modalBackdrop").classList.add("hidden");
    document.getElementById("interpretationModal").classList.add("hidden");
    document.getElementById("chatInterface").classList.add("hidden");
    document.getElementById("interpretationText").classList.remove("hidden");
    if (this.currentUtterance) {
      window.speechSynthesis.cancel();
    }
  },

  async getAIInterpretation(type) {
    try {
      this.currentInterpretationType = type;
      const loadingOverlay = document.getElementById("loadingOverlay");
      const modalBackdrop = document.getElementById("modalBackdrop");
      const interpretationModal = document.getElementById(
        "interpretationModal"
      );
      const interpretationText = document.getElementById("interpretationText");
      const chatInterface = document.getElementById("chatInterface");

      loadingOverlay.classList.remove("hidden");
      modalBackdrop.classList.remove("hidden");
      interpretationModal.classList.remove("hidden");
      chatInterface.classList.add("hidden");
      interpretationText.classList.remove("hidden");

      const response = await fetch("/get_ai_interpretation", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ type: type }),
      });

      const data = await response.json();
      loadingOverlay.classList.add("hidden");

      if (data.success) {
        this.lastInterpretation = data.interpretation;
        interpretationText.innerHTML = `<p class="mb-4 text-gray-200">${data.interpretation}</p>`;
      } else {
        interpretationText.innerHTML = `<p class="text-red-500">Hata: ${data.error}</p>`;
      }
    } catch (error) {
      console.error("AI yorumu alınırken hata:", error);
      document.getElementById("loadingOverlay").classList.add("hidden");
      alert("Yorum alınırken bir hata oluştu: " + error);
    }
  },

  startSpeech(text) {
    if (this.currentUtterance) {
      window.speechSynthesis.cancel();
    }
    this.currentUtterance = new SpeechSynthesisUtterance(text);
    this.currentUtterance.lang = "tr-TR";
    document.getElementById("playButton").classList.add("hidden");
    document.getElementById("pauseButton").classList.remove("hidden");
    window.speechSynthesis.speak(this.currentUtterance);
  },

  pauseSpeech() {
    window.speechSynthesis.pause();
    document.getElementById("pauseButton").classList.add("hidden");
    document.getElementById("playButton").classList.remove("hidden");
  },

  resumeSpeech() {
    window.speechSynthesis.resume();
    document.getElementById("playButton").classList.add("hidden");
    document.getElementById("pauseButton").classList.remove("hidden");
  },

  stopSpeech() {
    window.speechSynthesis.cancel();
    document.getElementById("pauseButton").classList.add("hidden");
    document.getElementById("playButton").classList.remove("hidden");
  },

  async showChatInterface() {
    try {
      const interpretationText = document.getElementById("interpretationText");
      const chatInterface = document.getElementById("chatInterface");
      const lastInterpretationDiv =
        document.getElementById("lastInterpretation");
      const chatHistory = document.getElementById("chatHistory");

      this.stopSpeech();

      interpretationText.classList.add("hidden");
      chatInterface.classList.remove("hidden");
      chatInterface.style.display = "flex";
      chatHistory.innerHTML = "";

      if (lastInterpretationDiv && this.lastInterpretation) {
        lastInterpretationDiv.textContent = this.lastInterpretation;
      }

      const response = await fetch("/start_chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          type: this.currentInterpretationType,
          last_interpretation: this.lastInterpretation,
        }),
      });

      const data = await response.json();
      if (data.success) {
        this.currentSessionId = data.session_id;
        this.appendMessage("ai", data.welcome_message);
        document.getElementById("messageInput").focus();
      }
    } catch (error) {
      console.error("Chat başlatma hatası:", error);
      alert("Sohbet başlatılırken bir hata oluştu: " + error);
    }
  },

  appendMessage(type, content) {
    const chatHistory = document.getElementById("chatHistory");
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${type}-message`;
    messageDiv.textContent = content;
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
  },

  async sendMessage() {
    const messageInput = document.getElementById("messageInput");
    const message = messageInput.value.trim();

    if (!message) return;

    this.appendMessage("user", message);
    messageInput.value = "";

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: message,
          session_id: this.currentSessionId,
          type: this.currentInterpretationType,
          last_interpretation: this.lastInterpretation,
        }),
      });

      const data = await response.json();
      if (data.success) {
        this.appendMessage("ai", data.response);
      } else {
        this.appendMessage("ai", "Üzgünüm, bir hata oluştu.");
      }
    } catch (error) {
      console.error("Mesaj gönderme hatası:", error);
      this.appendMessage("ai", "Üzgünüm, bir hata oluştu.");
    }
  },
};

// Event listener'ları
document.addEventListener("DOMContentLoaded", function () {
  // Modal kapama butonları
  if (document.getElementById("closeModalBtn")) {
    document
      .getElementById("closeModalBtn")
      .addEventListener("click", () => window.astro.closeModal());
  }
  if (document.getElementById("modalBackdrop")) {
    document.getElementById("modalBackdrop").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) window.astro.closeModal();
    });
  }

  // Ses kontrol butonları
  const playButton = document.getElementById("playButton");
  const pauseButton = document.getElementById("pauseButton");
  const stopButton = document.getElementById("stopButton");

  if (playButton) {
    playButton.addEventListener("click", () => {
      if (window.speechSynthesis.paused) {
        window.astro.resumeSpeech();
      } else {
        window.astro.startSpeech(
          document.getElementById("interpretationText").textContent
        );
      }
    });
  }

  if (pauseButton) {
    pauseButton.addEventListener("click", () => window.astro.pauseSpeech());
  }

  if (stopButton) {
    stopButton.addEventListener("click", () => window.astro.stopSpeech());
  }

  // Soru sor butonu
  if (document.getElementById("askQuestionBtn")) {
    document
      .getElementById("askQuestionBtn")
      .addEventListener("click", () => window.astro.showChatInterface());
  }

  // ESC tuşu ile modal kapatma
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") window.astro.closeModal();
  });

  // Mesaj gönderme butonları
  const sendButton = document.querySelector(".send-button");
  if (sendButton) {
    sendButton.addEventListener("click", () => window.astro.sendMessage());
  }

  const sendMessageBtn = document.getElementById("sendMessageBtn");
  if (sendMessageBtn) {
    sendMessageBtn.addEventListener("click", () => window.astro.sendMessage());
  }

  // Enter tuşu ile mesaj gönderme
  const messageInput = document.getElementById("messageInput");
  if (messageInput) {
    messageInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.astro.sendMessage();
      }
    });
  }

  // Form gönderimi event listener
  const astroForm = document.getElementById("astro-form");
  if (astroForm) {
    astroForm.addEventListener("submit", submitAstroForm);
  }

  /* Redundant: Handled in dashboard.html or other page-specific scripts
    const birthPlaceInput = document.getElementById( 'birth_place' );
    if ( birthPlaceInput ) {
        birthPlaceInput.addEventListener( 'input', ( e ) => {
            searchLocation( e.target.value, 'birth' );
        } );
    }

    const transitLocationInput = document.getElementById( 'transit_location_search' );
    if ( transitLocationInput ) {
        transitLocationInput.addEventListener( 'input', ( e ) => {
            searchLocation( e.target.value, 'transit' );
        } );
    }
    */
});

// Sayfa dışına tıklandığında sonuçları gizle
document.addEventListener("click", function (e) {
  const locationResults = document.getElementById("locationResults");
  if (
    locationResults &&
    !e.target.closest("#birth_place") &&
    !e.target.closest("#locationResults")
  ) {
    locationResults.classList.add("hidden");
  }
});

// Gezegen sembollerini döndüren yardımcı fonksiyon
function getPlanetSymbol(planetName) {
  const symbols = {
    Sun: "☉",
    Moon: "☽",
    Mercury: "☿",
    Venus: "♀",
    Mars: "♂",
    Jupiter: "♃",
    Saturn: "♄",
    Uranus: "♅",
    Neptune: "♆",
    Pluto: "♇",
    Chiron: " Chiron",
    Lilith: " Lilith", // İkonları yoksa isimleri
    "North Node": "☊",
    "South Node": "☋",
    Ascendant: "ASC",
    Midheaven: "MC",
    // Türkçe isimler için de ekleyebiliriz veya sunucudan gelen isimleri İngilizce'ye mapleyebiliriz.
    // Şimdilik İngilizce temelli bırakıyorum.
  };
  return symbols[planetName] || planetName;
}

// Natal verilerini HTML'e yerleştiren ana fonksiyon
function displayNatalData(astroData) {
  if (!astroData) {
    console.warn("displayNatalData: astroData bulunamadı.");
    return;
  }

  // 1. Doğum Haritası Özet Bilgileri (natal-chart-summary-info)
  const birthDatetimeEl = document.getElementById("natal-birth-datetime");
  const birthLocationEl = document.getElementById("natal-birth-location");
  const houseSystemEl = document.getElementById("natal-house-system");
  const ascendantInfoEl = document.getElementById("natal-ascendant-info");
  const mcInfoEl = document.getElementById("natal-mc-info");

  if (astroData.birth_info) {
    if (birthDatetimeEl)
      birthDatetimeEl.textContent = `${astroData.birth_info.date || ""} ${
        astroData.birth_info.time || ""
      }`;
    if (birthLocationEl)
      birthLocationEl.textContent =
        astroData.birth_info.location_name ||
        (astroData.birth_info.location
          ? `${astroData.birth_info.location.latitude}, ${astroData.birth_info.location.longitude}`
          : "Bilinmiyor");
  }
  if (houseSystemEl)
    houseSystemEl.textContent = astroData.house_system || "Bilinmiyor";

  if (astroData.natal_summary) {
    if (ascendantInfoEl) {
      ascendantInfoEl.textContent = `${
        astroData.natal_summary.ascendant_sign || ""
      } ${
        astroData.natal_summary.ascendant_degree !== undefined
          ? parseFloat(astroData.natal_summary.ascendant_degree).toFixed(2) +
            "°"
          : ""
      }`;
    }
    if (mcInfoEl) {
      mcInfoEl.textContent = `${astroData.natal_summary.mc_sign || ""} ${
        astroData.natal_summary.mc_degree !== undefined
          ? parseFloat(astroData.natal_summary.mc_degree).toFixed(2) + "°"
          : ""
      }`;
    }
  }

  // 2. Natal Yorum Özetleri (natal-summary-interpretations)
  const summaryInterpretationsEl = document.getElementById(
    "natal-summary-interpretations"
  );
  if (summaryInterpretationsEl) {
    summaryInterpretationsEl.innerHTML =
      '<h3 class="text-lg font-semibold mb-4">Doğum Haritası Yorum Özeti</h3>'; // Başlığı koru
    if (
      astroData.natal_summary_interpretation &&
      astroData.natal_summary_interpretation.length > 0
    ) {
      const interpretationsContainer = document.createElement("div");
      interpretationsContainer.className = "space-y-3"; // Orijinal Jinja'daki grid grid-cols-1 gap-3 yerine space-y-3 daha uygun olabilir

      astroData.natal_summary_interpretation.forEach((item) => {
        const itemDiv = document.createElement("div");
        itemDiv.className = "p-3 rounded-lg text-sm"; // Temel sınıflar

        let contentHtml = "";
        let iconHtml = "";
        let titleText = "";

        // Stil ve ikon belirleme (Jinja'daki mantığa benzer)
        if (item.includes("Element Dağılımı:")) {
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-blue-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-blue-500 mr-3"><i class="fas fa-wind text-white"></i></div>';
          titleText = "Element Dağılımı";

          const stats = item.split(":")[1].trim().split(",");
          let statsHtml = '<div class="ml-11 grid grid-cols-2 gap-2 mt-1">';
          stats.forEach((stat) => {
            const elementName = stat.split(":")[0].trim();
            let bgColor = "bg-slate-600"; // Default
            if (elementName.includes("Ateş")) bgColor = "bg-red-500";
            else if (elementName.includes("Toprak")) bgColor = "bg-amber-600";
            else if (elementName.includes("Hava")) bgColor = "bg-sky-500";
            else if (elementName.includes("Su")) bgColor = "bg-blue-500";
            statsHtml += `
                            <div class="flex items-center">
                                <div class="w-5 h-5 flex items-center justify-center rounded-full mr-2 ${bgColor}"></div>
                                <span class="text-xs text-slate-300">${stat.trim()}</span>
                            </div>`;
          });
          statsHtml += "</div>";
          contentHtml = `<div><div class="flex items-center mb-1">${iconHtml}<p class="text-slate-200 font-medium">${titleText}</p></div>${statsHtml}</div>`;
        } else if (item.includes("Element:")) {
          // 'Element Dağılımı'ndan sonra kontrol etmeli
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-blue-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-blue-500 mr-3"><i class="fas fa-wind text-white"></i></div>';
          contentHtml = `<div class="flex items-center">${iconHtml}<p class="text-slate-200">${item}</p></div>`;
        } else if (item.includes("Nitelik:")) {
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-green-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-green-500 mr-3"><i class="fas fa-exchange-alt text-white"></i></div>';
          contentHtml = `<div class="flex items-center">${iconHtml}<p class="text-slate-200">${item}</p></div>`;
        } else if (item.includes("Polarite:")) {
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-purple-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-purple-500 mr-3"><i class="fas fa-yin-yang text-white"></i></div>';
          contentHtml = `<div class="flex items-center">${iconHtml}<p class="text-slate-200">${item}</p></div>`;
        } else if (
          item.includes("Güneş-Ay Fazı:") ||
          item.includes("Güneş-Ay İlişkisi:")
        ) {
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-yellow-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-yellow-500 mr-3"><i class="fas fa-moon text-white"></i></div>';
          contentHtml = `<div class="flex items-center">${iconHtml}<p class="text-slate-200">${item}</p></div>`;
        } else if (item.includes("Yükselen Yorumu:")) {
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-pink-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-pink-500 mr-3"><i class="fas fa-arrow-up text-white"></i></div>';
          contentHtml = `<div class="flex items-center">${iconHtml}<p class="text-slate-200">${item}</p></div>`;
        } else if (item.match(/\d+\.\s*Ev:/i) || item.startsWith("Ev:")) {
          // "1. Ev:", "Ev: Koç" gibi formatlar
          itemDiv.classList.add(
            "bg-gradient-to-r",
            "from-slate-800",
            "to-indigo-900"
          );
          iconHtml =
            '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-indigo-500 mr-3"><i class="fas fa-home text-white"></i></div>';

          const parts = item.split(":");
          const houseNumberText = parts[0].trim();
          const planetsText = parts.length > 1 ? parts[1].trim() : "";
          const planets = planetsText
            ? planetsText
                .split(",")
                .map((p) => p.trim())
                .filter((p) => p)
            : [];

          let planetsHtml = '<div class="ml-11 flex flex-wrap gap-2 mt-1">';
          if (planets.length > 0) {
            planets.forEach((planet) => {
              let bgColor = "bg-slate-700 text-slate-200"; // Default
              if (
                planet.toLowerCase().includes("güneş") ||
                planet.toLowerCase().includes("sun")
              )
                bgColor = "bg-yellow-700 text-yellow-200";
              else if (
                planet.toLowerCase().includes("ay") ||
                planet.toLowerCase().includes("moon")
              )
                bgColor = "bg-blue-700 text-blue-200";
              else if (
                planet.toLowerCase().includes("merkür") ||
                planet.toLowerCase().includes("mercury")
              )
                bgColor = "bg-purple-700 text-purple-200";
              else if (
                planet.toLowerCase().includes("venüs") ||
                planet.toLowerCase().includes("venus")
              )
                bgColor = "bg-pink-700 text-pink-200";
              else if (planet.toLowerCase().includes("mars"))
                bgColor = "bg-red-700 text-red-200";
              else if (
                planet.toLowerCase().includes("jüpiter") ||
                planet.toLowerCase().includes("jupiter")
              )
                bgColor = "bg-orange-700 text-orange-200";
              else if (
                planet.toLowerCase().includes("satürn") ||
                planet.toLowerCase().includes("saturn")
              )
                bgColor = "bg-gray-700 text-gray-200";
              // Diğer gezegenler eklenebilir
              planetsHtml += `<span class="px-2 py-1 text-xs rounded-full ${bgColor}">${planet}</span>`;
            });
          } else {
            planetsHtml +=
              '<span class="text-xs text-slate-400">Bu evde gezegen yok veya belirtilmemiş.</span>';
          }
          planetsHtml += "</div>";
          contentHtml = `<div><div class="flex items-center mb-1">${iconHtml}<p class="text-slate-200 font-medium">${houseNumberText}</p></div>${planetsHtml}</div>`;
        } else {
          // Diğer genel yorumlar
          itemDiv.classList.add("border", "border-slate-700");
          if (item.length < 50) {
            // Kısa genel yorumlar için ikon
            iconHtml =
              '<div class="w-8 h-8 flex items-center justify-center rounded-full bg-slate-500 mr-3"><i class="fas fa-info-circle text-white"></i></div>';
            contentHtml = `<div class="flex items-center">${iconHtml}<p class="text-slate-200 font-medium">${item}</p></div>`;
          } else {
            contentHtml = `<p class="text-slate-300">${item}</p>`;
          }
        }
        itemDiv.innerHTML = contentHtml;
        interpretationsContainer.appendChild(itemDiv);
      });
      summaryInterpretationsEl.appendChild(interpretationsContainer);
    } else {
      summaryInterpretationsEl.innerHTML +=
        '<p class="text-slate-400">Yorum özeti bulunamadı.</p>';
    }
  }

  // 3. Ana Gezegen Pozisyonları (natal-main-planets-list)
  const mainPlanetsListEl = document.getElementById("natal-main-planets-list");
  if (mainPlanetsListEl) {
    mainPlanetsListEl.innerHTML =
      '<h3 class="text-lg font-semibold mb-4">Temel Pozisyonlar</h3>'; // Başlığı koru
    const planetsContainer = document.createElement("div");
    planetsContainer.className = "space-y-4";

    const createPlanetElement = (name, data, isPoint = false) => {
      const planetDiv = document.createElement("div");
      planetDiv.className = "flex items-center";

      let iconClass = "fas fa-question-circle"; // Default icon
      let bgColor = "bg-slate-500";
      const displayName = name;

      const planetKeyLower = name.toLowerCase();

      if (planetKeyLower.includes("sun") || planetKeyLower.includes("güneş")) {
        iconClass = "fas fa-sun";
        bgColor = "bg-yellow-500";
      } else if (
        planetKeyLower.includes("moon") ||
        planetKeyLower.includes("ay")
      ) {
        iconClass = "fas fa-moon";
        bgColor = "bg-blue-400";
      } else if (
        planetKeyLower.includes("mercury") ||
        planetKeyLower.includes("merkür")
      ) {
        iconClass = "fas fa-brain";
        bgColor = "bg-purple-400";
      } else if (
        planetKeyLower.includes("venus") ||
        planetKeyLower.includes("venüs")
      ) {
        iconClass = "fas fa-venus";
        bgColor = "bg-pink-400";
      } else if (planetKeyLower.includes("mars")) {
        iconClass = "fas fa-mars";
        bgColor = "bg-red-500";
      } else if (
        planetKeyLower.includes("jupiter") ||
        planetKeyLower.includes("jüpiter")
      ) {
        iconClass = "fas fa-jupiter";
        bgColor = "bg-orange-500";
      } else if (
        planetKeyLower.includes("saturn") ||
        planetKeyLower.includes("satürn")
      ) {
        iconClass = "fas fa-saturn";
        bgColor = "bg-yellow-700";
      } else if (
        planetKeyLower.includes("uranus") ||
        planetKeyLower.includes("uranüs")
      ) {
        iconClass = "fas fa-uranus";
        bgColor = "bg-sky-500";
      } else if (
        planetKeyLower.includes("neptune") ||
        planetKeyLower.includes("neptün")
      ) {
        iconClass = "fas fa-neptune";
        bgColor = "bg-blue-600";
      } else if (
        planetKeyLower.includes("pluto") ||
        planetKeyLower.includes("plüton")
      ) {
        iconClass = "fas fa-meteor";
        bgColor = "bg-indigo-600";
      } else if (
        planetKeyLower.includes("ascendant") ||
        planetKeyLower.includes("yükselen") ||
        name.toUpperCase() === "ASC"
      ) {
        iconClass = "fas fa-arrow-alt-circle-up";
        bgColor = "bg-green-500";
      } else if (
        planetKeyLower.includes("midheaven") ||
        name.toUpperCase() === "MC"
      ) {
        iconClass = "fas fa-crosshairs";
        bgColor = "bg-cyan-500";
      }

      const sign = data.sign || "";
      const degree =
        data.degree !== undefined
          ? parseFloat(data.degree).toFixed(2) + "°"
          : "";
      const house = data.house
        ? `${data.house}. Evde`
        : isPoint
        ? ""
        : "Ev bilgisi yok";

      planetDiv.innerHTML = `
                <div class="planet-icon ${bgColor} text-slate-900">
                    <i class="${iconClass}"></i>
                </div>
                <div>
                    <p class="font-medium">${displayName} ${sign}'de</p>
                    <p class="text-sm text-slate-400">${degree} ${house}</p>
                </div>
            `;
      return planetDiv;
    };

    if (astroData.natal_planet_positions) {
      const planetOrder = [
        "Sun",
        "Moon",
        "Mercury",
        "Venus",
        "Mars",
        "Jupiter",
        "Saturn",
        "Uranus",
        "Neptune",
        "Pluto",
      ];
      planetOrder.forEach((planetName) => {
        if (astroData.natal_planet_positions[planetName]) {
          planetsContainer.appendChild(
            createPlanetElement(
              planetName,
              astroData.natal_planet_positions[planetName]
            )
          );
        }
      });
    }

    if (astroData.natal_summary) {
      if (astroData.natal_summary.ascendant_sign) {
        planetsContainer.appendChild(
          createPlanetElement(
            "Yükselen (ASC)",
            {
              sign: astroData.natal_summary.ascendant_sign,
              degree: astroData.natal_summary.ascendant_degree,
            },
            true
          )
        );
      }
      if (astroData.natal_summary.mc_sign) {
        planetsContainer.appendChild(
          createPlanetElement(
            "MC (Tepe Noktası)",
            {
              sign: astroData.natal_summary.mc_sign,
              degree: astroData.natal_summary.mc_degree,
            },
            true
          )
        );
      }
    }

    if (planetsContainer.hasChildNodes()) {
      mainPlanetsListEl.appendChild(planetsContainer);
    } else {
      mainPlanetsListEl.innerHTML +=
        '<p class="text-slate-400">Gezegen pozisyonları bulunamadı.</p>';
    }
  }

  // Diğer sekmeler için de benzer veri yükleme fonksiyonları eklenebilir.
  // displayTransitData(astroData);
  // displayProgressionsData(astroData);
  // ...
}

// Sayfa yüklendiğinde çalışacak fonksiyonlar
window.onload = function () {
  console.log("window.onload çağrıldı."); // DEBUG
  const astroDataStr = localStorage.getItem("astro_data");
  // Template'den gelen astroData varsa override etme
  if (!window.astroData) {
    window.astroData = null;
  }
  window.userName = null;
  window.birthPlaceName = null;

  console.log(
    "LocalStorage'dan astro_data_str (ilk 100 char):",
    astroDataStr ? astroDataStr.substring(0, 100) + "..." : "yok"
  ); // DEBUG

  try {
    if (astroDataStr) {
      window.astroData = JSON.parse(astroDataStr);
      // Loglarken tüm objeyi değil, bir kısmını loglamak daha iyi olabilir, çok büyük olabilir.
      console.log(
        "LocalStorage'dan astro_data yüklendi (JSON.stringify ile ilk 200 char):",
        window.astroData
          ? JSON.stringify(window.astroData).substring(0, 200) + "..."
          : "parse edilemedi"
      );
    } else {
      console.warn("LocalStorage'da astro_data bulunamadı.");
    }
    window.userName = localStorage.getItem("user_name");
    window.birthPlaceName = localStorage.getItem("birth_place_name");
    console.log("LocalStorage'dan userName yüklendi:", window.userName);
    console.log(
      "LocalStorage'dan birthPlaceName yüklendi:",
      window.birthPlaceName
    );
  } catch (error) {
    console.error("LocalStorage verisi yüklenirken hata oluştu:", error);
  }

  // Yeni veri yükleme fonksiyonunu çağır
  if (window.astroData) {
    console.log("displayNatalData çağrılacak."); // DEBUG
    displayNatalData(window.astroData);

    // Debug bilgilerini güncelle
    const userNameEl = document.getElementById("debug-user-name");
    const birthDateEl = document.getElementById("debug-birth-date");
    const positionsEl = document.getElementById("debug-positions");
    const transitDateEl = document.getElementById("debug-transit-date");
    const dataStatusEl = document.getElementById("data-status");

    // window.userName globalde, window.astroData.user_name yerine bunu kullanalım
    if (userNameEl) userNameEl.textContent = window.userName || "Bilinmiyor";

    if (
      birthDateEl &&
      window.astroData.birth_info &&
      window.astroData.birth_info.datetime
    ) {
      const [datePart, timePart] =
        window.astroData.birth_info.datetime.split(" ");
      birthDateEl.textContent = `${datePart || ""} ${timePart || ""}`;
    } else if (birthDateEl) {
      birthDateEl.textContent = "Bilinmiyor";
    }

    if (positionsEl)
      positionsEl.textContent =
        window.astroData.natal_planet_positions &&
        Object.keys(window.astroData.natal_planet_positions).length > 0
          ? "Mevcut"
          : "Yok";
    if (transitDateEl && window.astroData.transit_date)
      transitDateEl.textContent = window.astroData.transit_date;

    if (dataStatusEl) {
      dataStatusEl.textContent = "Veri Yüklendi";
      dataStatusEl.className = "px-2 py-1 rounded bg-green-700 text-white"; // Orijinal class'ı koruyalım
    }

    // Header'daki özet bilgileri güncelle (birth-info-summary ID'li div için)
    const birthInfoSummaryDiv = document.getElementById("birth-info-summary"); // Bu ID'li div'i hedefliyoruz
    if (birthInfoSummaryDiv) {
      // Bu div içindeki span'leri güncelleyeceğiz
      const birthDatetimeSummaryEl = document.getElementById(
        "birth-datetime-summary"
      );
      const birthLocationSummaryEl = document.getElementById(
        "birth-location-summary"
      );
      const sunSignSummaryEl = document.getElementById("sun-sign-summary");
      const moonSignSummaryEl = document.getElementById("moon-sign-summary");
      const ascendantSignSummaryEl = document.getElementById(
        "ascendant-sign-summary"
      );

      let showSummary = false;

      if (window.astroData.birth_info) {
        if (birthDatetimeSummaryEl && window.astroData.birth_info.datetime) {
          const [datePart, timePart] =
            window.astroData.birth_info.datetime.split(" ");
          birthDatetimeSummaryEl.textContent = `${datePart || ""} ${
            timePart || ""
          }`;
          showSummary = true;
        } else if (birthDatetimeSummaryEl) {
          birthDatetimeSummaryEl.textContent = "-";
        }

        // Doğum yeri için localStorage'dan okunan window.birthPlaceName'i kullanalım
        if (birthLocationSummaryEl) {
          birthLocationSummaryEl.textContent =
            window.birthPlaceName || "Bilinmiyor";
          if (window.birthPlaceName) showSummary = true;
        }
      }

      if (window.astroData.natal_planet_positions) {
        if (sunSignSummaryEl && window.astroData.natal_planet_positions.Sun) {
          sunSignSummaryEl.textContent =
            window.astroData.natal_planet_positions.Sun.sign || "-";
          if (window.astroData.natal_planet_positions.Sun.sign)
            showSummary = true;
        } else if (sunSignSummaryEl) {
          sunSignSummaryEl.textContent = "-";
        }
        if (moonSignSummaryEl && window.astroData.natal_planet_positions.Moon) {
          moonSignSummaryEl.textContent =
            window.astroData.natal_planet_positions.Moon.sign || "-";
          if (window.astroData.natal_planet_positions.Moon.sign)
            showSummary = true;
        } else if (moonSignSummaryEl) {
          moonSignSummaryEl.textContent = "-";
        }
      }

      if (window.astroData.natal_summary) {
        if (ascendantSignSummaryEl) {
          ascendantSignSummaryEl.textContent =
            window.astroData.natal_summary.ascendant_sign || "-";
          if (window.astroData.natal_summary.ascendant_sign) showSummary = true;
        } else if (ascendantSignSummaryEl) {
          ascendantSignSummaryEl.textContent = "-";
        }
      }

      if (showSummary) {
        birthInfoSummaryDiv.classList.remove("hidden");
        console.log("Header özet bilgileri güncellendi ve gösteriliyor."); // DEBUG
      } else {
        birthInfoSummaryDiv.classList.add("hidden");
        console.log("Header özet bilgileri için yeterli veri yok, gizlendi."); // DEBUG
      }
    }
  } else {
    console.warn(
      "window.astroData yüklenemediği için displayNatalData çağrılmayacak ve debug/header bilgileri güncellenmeyecek."
    ); // DEBUG
    // Veri yoksa debug panelini ve header'ı güncelle
    const dataStatusEl = document.getElementById("data-status");
    if (dataStatusEl) {
      dataStatusEl.textContent = "Veri Yok";
      dataStatusEl.className = "px-2 py-1 rounded bg-red-800 text-white"; // Orijinal class'ı koruyalım
    }
    const birthInfoSummaryDiv = document.getElementById("birth-info-summary");
    if (birthInfoSummaryDiv) {
      birthInfoSummaryDiv.classList.add("hidden"); // Veri yoksa header'ı gizle
    }
    // Eğer veri yoksa, natal sekmesindeki alanları da "Veri yok" olarak ayarlayalım
    if (document.getElementById("natal-birth-datetime"))
      document.getElementById("natal-birth-datetime").textContent =
        "Veri hesaplanmadı.";
    if (document.getElementById("natal-birth-location"))
      document.getElementById("natal-birth-location").textContent =
        "Veri hesaplanmadı.";
    if (document.getElementById("natal-house-system"))
      document.getElementById("natal-house-system").textContent =
        "Veri hesaplanmadı.";
    if (document.getElementById("natal-ascendant-info"))
      document.getElementById("natal-ascendant-info").textContent =
        "Veri hesaplanmadı.";
    if (document.getElementById("natal-mc-info"))
      document.getElementById("natal-mc-info").textContent =
        "Veri hesaplanmadı.";
    if (document.getElementById("natal-summary-interpretations"))
      document.getElementById("natal-summary-interpretations").innerHTML =
        '<h3 class="text-lg font-semibold mb-4">Doğum Haritası Yorum Özeti</h3><p class="text-slate-400">Yorum özeti verisi bulunamadı.</p>';
    if (document.getElementById("natal-main-planets-list"))
      document.getElementById("natal-main-planets-list").innerHTML =
        '<h3 class="text-lg font-semibold mb-4">Temel Pozisyonlar</h3><p class="text-slate-400">Gezegen pozisyonları verisi bulunamadı.</p>';
  }

  // Eski veri yükleme kısımları (new_result.html'de artık bu ID'ler yoksa yorumda kalabilir veya silinebilir)
  /*
    if ( window.astroData && window.astroData.natal_chart ) {
        const natalChartData = window.astroData.natal_chart;

        // Özet alanını doldur
        const natalSummaryContainer = document.getElementById( 'new-natal-summary-container' );
        if ( natalSummaryContainer ) {
            natalSummaryContainer.innerHTML = `
                <h3 class="text-lg font-semibold text-indigo-300 mb-2">Temel Özellikler</h3>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div class="key-indicator-item">
                        <span class="indicator-label">Güneş Burcu</span>
                        <span class="indicator-value">${natalChartData.sun_sign || '-'}</span>
                    </div>
                    <div class="key-indicator-item">
                        <span class="indicator-label">Ay Burcu</span>
                        <span class="indicator-value">${natalChartData.moon_sign || '-'}</span>
                    </div>
                    <div class="key-indicator-item">
                        <span class="indicator-label">Yükselen</span>
                        <span class="indicator-value">${natalChartData.ascendant || '-'}</span>
                    </div>
                    <div class="key-indicator-item">
                        <span class="indicator-label">MC</span>
                        <span class="indicator-value">${natalChartData.mc || '-'}</span>
                    </div>
                </div>
            `;
        }

        // Gezegen pozisyonlarını tabloya ekle
        const planetsTableBody = document.getElementById( 'planets-table-body' );
        if ( planetsTableBody && natalChartData.planets ) {
            planetsTableBody.innerHTML = '';
            natalChartData.planets.forEach( planet => {
                const row = document.createElement( 'tr' );
                row.innerHTML = `
                    <td>${planet.name}</td>
                    <td>${planet.sign}</td>
                    <td>${planet.degree}</td>
                    <td>${planet.house}</td>
                    <td>${planet.retrograde ? '<span class="table-badge table-badge-retro">R</span>' : ''}</td>
                    <td><button class="detail-button" data-planet="${planet.name}">Detaylar</button></td>
                `;
                planetsTableBody.appendChild( row );
            } );
        }

        // Evler akordeonunu doldur
        const housesContent = document.getElementById( 'houses-content' );
        if ( housesContent && natalChartData.houses ) {
            housesContent.innerHTML = '';
            for ( let i = 1; i <= 12; i++ ) {
                const house = natalChartData.houses[i.toString()];
                if ( house ) {
                    const houseCard = document.createElement( 'div' );
                    houseCard.className = 'house-card fire-theme';
                    houseCard.innerHTML = `
                        <h4 class="house-title"><i class="fas fa-home"></i> ${i}. Ev</h4>
                        <p class="house-sign">${house.sign} ${house.degree}</p>
                        <p class="house-ruler">Yönetici: ${house.ruler}</p>
                        <p class="house-keywords">Anahtar Kelimeler: ${house.keywords.join( ', ' )}</p>
                    `;
                    housesContent.appendChild( houseCard );
                }
            }
        }
    }
    */
};
