/**
 * Tema değiştirme ve yönetme işlevleri
 */
document.addEventListener('DOMContentLoaded', () => {
    // Tema yönetimi
    const themeToggle = document.getElementById('themeToggle');
    const html = document.documentElement;
    const themeIcon = document.querySelector('.theme-icon');
    
    // Sistem temasını kontrol et
    const preferslightMode = window.matchMedia('(prefers-color-scheme: light)').matches;
    const savedTheme = localStorage.getItem('theme') || (preferslightMode ? 'dark' : 'light');
    
    // Temayı uygula
    applyTheme(savedTheme);
    
    // Tema değiştirme düğmesine tıklama olayını ekle
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            applyTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }
    
    // Temayı uygulama fonksiyonu
    function applyTheme(theme) {
        html.setAttribute('data-theme', theme);
        
        // Tema ikonunu güncelle
        if (themeIcon) {
            themeIcon.textContent = theme === 'dark' ? '🌙' : '☀️';
        }
        
        // Meta temasını güncelle
        const metaThemeColor = document.querySelector('meta[name="theme-color"]');
        if (metaThemeColor) {
            metaThemeColor.setAttribute('content', 
                theme === 'dark' ? '#24283b' : '#f0f2f5');
        }
    }
    
    // Sistem teması değişikliğini dinle
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (!localStorage.getItem('theme')) {
            // Kullanıcı manuel tema seçimi yapmamışsa sistem temasını takip et
            applyTheme(e.matches ? 'dark' : 'light');
        }
    });
});

// Dark Mode İşlemleri
document.addEventListener('DOMContentLoaded', function() {
    // Dark mode ayarını localStorage'dan al
    const darkMode = localStorage.getItem('darkMode');
    const darkModeToggle = document.getElementById('darkModeToggle');
    
    // Sayfa yüklendiğinde mevcut temayı ayarla
    if (darkMode === 'true' || 
        (darkMode === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        enableDarkMode();
    } else {
        disableDarkMode();
    }
    
    // Dark mode toggle butonuna tıklandığında
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', function() {
            if (document.documentElement.classList.contains('dark')) {
                disableDarkMode();
            } else {
                enableDarkMode();
            }
        });
    }
    
    // Dark mode'u aktifleştir
    function enableDarkMode() {
        document.documentElement.classList.add('dark');
        localStorage.setItem('darkMode', 'true');
        updateIcons(true);
    }
    
    // Dark mode'u devre dışı bırak
    function disableDarkMode() {
        document.documentElement.classList.remove('dark');
        localStorage.setItem('darkMode', 'false');
        updateIcons(false);
    }
    
    // Dark/light ikonlarını güncelle
    function updateIcons(isDark) {
        const lightIcon = document.getElementById('lightIcon');
        const darkIcon = document.getElementById('darkIcon');
        
        if (lightIcon && darkIcon) {
            if (isDark) {
                lightIcon.classList.remove('hidden');
                darkIcon.classList.add('hidden');
            } else {
                lightIcon.classList.add('hidden');
                darkIcon.classList.remove('hidden');
            }
        }
    }
    
    // Sistem teması değiştiğinde otomatik güncelleme (opsiyonel)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
        if (e.matches) {
            enableDarkMode();
        } else {
            disableDarkMode();
        }
    });
});
