"""
ORBIS AI Service
- Firestore'dan provider ayarlarını okur (config/ai_settings)
- Sıralı yedekleme: Aktif -> Y-1 -> Y-2 -> Y-3
- Async HTTP çağrıları
"""
import os
import json
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

import aiohttp
from openai import OpenAI

from extensions import cache
from utils import Constants

logger = logging.getLogger(__name__)


class AIService:
    BASE_RULES = """
## KESİN KURALLAR
### 1. YASAK TERİMLER (ASLA KULLANMA)
- Gezegen isimleri: Mars, Venüs, Satürn, Jüpiter, Merkür, Ay, Güneş, Uranüs, Neptün, Plüton
- Burç isimleri: Koç, Boğa, İkizler, Yengeç, Aslan, Başak, Terazi, Akrep, Yay, Oğlak, Kova, Balık
- Ev numaraları: 1. ev, 7. ev, 10. ev vb.
- Açı isimleri: kavuşum, karşıt, üçgen, kare, altmışlık, kuintil
- Teknik terimler: transit, progresyon, natal, ascendant, midheaven, düğüm, retrograd
### 2. DİL VE ÜSLUP
- Sade, anlaşılır Türkçe
- Doğrudan ve net ifadeler
- Mistik/ezoterik dil KULLANMA
- Kişiye adıyla hitap et, samimi ama profesyonel
### 3. UZUNLUK (ÖNEMLİ)
- Yanitin en az 1500 kelime olsun; bu zorunludur, daha kisa yanit yazma.
- Konulari tam ac, yarida birakma. Tum bolumleri (kariyer, iliskiler, saglik, finans, spiritüel gelisim, donemsel tavsiyeler) detayli sekilde isle.
- Her bolum en az 3-4 paragraf icersin, ornekler ve somut tavsiyeler ver.
"""

    # ════════════════════════════════════════════════════════════════════
    # VERİ FİLTRELEME — 25 hesaplama → 13 analiz türü
    # Her hesaplama en az 1 analiz türünde kullanılır, hiçbiri boşa gitmez.
    # ════════════════════════════════════════════════════════════════════
    DATA_FILTER = {
        "birth_chart": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "natal_additional_points",
        ],
        "relationship": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "natal_additional_points",
            "natal_antiscia", "natal_dignity_scores",
            "natal_arabic_parts", "natal_declinations",
            "natal_midpoint_analysis", "navamsa_chart",
            "natal_lunation_cycle", "natal_fixed_stars",
        ],
        "psychological_karmic": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "natal_additional_points",
            "natal_dignity_scores", "natal_declinations",
            "natal_midpoint_analysis", "deep_harmonic_analysis",
            "natal_lunation_cycle", "natal_fixed_stars",
            "vimshottari_dasa", "firdaria_periods",
            "eclipses_nearby_birth", "natal_antiscia",
        ],
        "daily": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "transit_positions", "transit_to_natal_aspects",
            "natal_aspects", "natal_additional_points",
            "solar_return_chart", "lunar_return_chart",
            "natal_lunation_cycle",
        ],
        "transits": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "transit_positions", "transit_to_natal_aspects",
            "solar_return_chart", "lunar_return_chart",
            "natal_aspects", "natal_declinations",
            "eclipses_nearby_current", "natal_lunation_cycle",
            "firdaria_periods", "natal_fixed_stars",
        ],
        "short_term": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "transit_positions", "transit_to_natal_aspects",
            "solar_return_chart", "lunar_return_chart",
            "natal_aspects", "eclipses_nearby_current",
            "natal_lunation_cycle",
        ],
        "long_term": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "transit_positions", "transit_to_natal_aspects",
            "vimshottari_dasa", "firdaria_periods",
            "solar_return_chart", "deep_harmonic_analysis",
            "eclipses_nearby_current", "natal_lunation_cycle",
            "natal_aspects",
        ],
        "career": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "natal_dignity_scores",
            "natal_midpoint_analysis", "natal_fixed_stars",
            "solar_return_chart", "firdaria_periods",
            "transit_positions", "transit_to_natal_aspects",
            "natal_arabic_parts",
        ],
        "health": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "natal_fixed_stars",
            "natal_declinations", "solar_return_chart",
            "transit_positions", "transit_to_natal_aspects",
        ],
        "finance": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "natal_arabic_parts",
            "natal_part_of_fortune", "natal_dignity_scores",
            "solar_return_chart", "transit_positions",
            "transit_to_natal_aspects",
        ],
        "spiritual": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_aspects", "deep_harmonic_analysis",
            "navamsa_chart", "vimshottari_dasa",
            "natal_lunation_cycle", "natal_fixed_stars",
            "natal_antiscia", "natal_declinations",
            "natal_midpoint_analysis",
        ],
        "summary": [
            "natal_planet_positions", "natal_houses", "natal_ascendant",
            "natal_summary_interpretation",
            "transit_positions",
        ],
    }

    # Her analiz türü için özel prompt (kapsamlı ama sadece ilgili veriyle)
    TYPE_PROMPTS = {
        "birth_chart": """
## DOĞUM HARİTASI VE KARAKTER ANALİZİ
Yukarıdaki verileri kullanarak kapsamlı bir doğum haritası analizi yap.
Şu başlıkları detaylıca işle:
1. Yükselen burcun kişiliğe etkisi — dış dünyaya yansıyan karakter
2. Ay burcunun duygusal yapıya etkisi — iç dünya ve ihtiyaçlar
3. Güneş burcunun temel karaktere etkisi — ego ve yaşam amacı
4. Gezegenlerin ev yerleşimleri — hayatın hangi alanında hangi enerji
5. Önemli açılar ve kişilik dinamikleri (büyük üçgen, T-kare, grand cross varsa)
6. Vimshottari Dasha dönemi ve Firdaria periyotlarına göre yaşam döngüleri
7. Vedic Navamsa haritasından evlilik/partnerlik potansiyeli
8. Doğum tutulmalarının yaşam temasına etkisi
""",
        "relationship": """
## İLİŞKİ ANALİZİ
Yukarıdaki verileri kullanarak ilişki potansiyelini ve dinamiklerini analiz et:
1. Venüs ve Mars yerleşimleri — aşk ve arzu dili
2. 5. ev (romantizm) ve 7. ev (partnerlik) vurguları
3. Lilith'in konumu — bastırılan arzular ve gölge yönler
4. Ay düğümleri (Kuzey/Güney) — ilişkilerdeki kadersel yolculuk
5. Arap noktalarından evlilik ve ilişki göstergeleri
6. Navamsa haritasından partner profili
7. Deklinasyon paralelleri — manyetik çekim dinamikleri
8. Sabit yıldızların romantik etkileri
""",
        "psychological_karmic": """
## PSİKOLOJİK VE KARMİK ANALİZ
Yukarıdaki verileri kullanarak derinlemesine psikolojik ve karmik analiz yap:
1. Satürn yerleşimi — karmik dersler, korkular, sınırlanma alanları
2. Plüton ve 8. ev — dönüşüm, güç dinamikleri, travma noktaları
3. Chiron — şifa alanı, en derin yara ve iyileşme potansiyeli
4. 12. ev gezegenleri — bilinçaltı, bastırılanlar, geçmiş yaşam izleri
5. Sert açılar (kare, karşıt) — iç çatışma ve büyüme alanları
6. Vimshottari Dasha — karmik zamanlama ve dönem dersleri
7. Deep harmonic (H7, H9) — ilişkisel ve spiritüel titreşimler
8. Doğum tutulmaları — ruhsal sözleşme ve misyon
""",
        "daily": """
## GÜNLÜK YORUM
Yukarıdaki verileri kullanarak bugünün enerjilerini yorumla:
1. Günün transit açıları ve etkileri
2. Ay'ın bugünkü konumu — duygusal ton
3. Solar ve Lunar Return'den bugünün teması
4. Günlük pratik tavsiyeler (iletişim, kararlar, enerji yönetimi)
5. Olumlu ve zorlayıcı saat dilimleri
""",
        "transits": """
## TRANSİT ANALİZİ
Yukarıdaki verileri kullanarak transit etkilerini detaylı analiz et:
1. Büyük gezegen transitleri (Jüpiter, Satürn, Uranüs, Neptün, Plüton) — uzun vadeli etkiler
2. Transit-natal açıları ve ev etkileşimleri
3. Solar Return yıllık teması
4. Lunar Return aylık teması
5. Yakın dönem tutulmalarının etkisi
6. Firdaria periyotlarına göre yaşam döngüleri
7. Transit sabit yıldız etkileri
""",
        "short_term": """
## KISA VADELİ ÖNGÖRÜ (1-3 AY)
Yukarıdaki verileri kullanarak önümüzdeki 1-3 aylık dönemi analiz et:
1. Hızlı gezegen transitleri ve tetikleyeceği olaylar
2. Ay düğümleri ve tutulmalar — kadersel dönemeçler
3. Solar/Lunar Return dönemsel mesajları
4. Fırsat pencereleri ve dikkat edilmesi gereken tarihler
5. Kariyer, ilişki, sağlık ve finans başlıklarında kısa vadeli tavsiyeler
""",
        "long_term": """
## UZUN VADELİ ÖNGÖRÜ (1-5 YIL)
Yukarıdaki verileri kullanarak önümüzdeki 1-5 yıllık dönemi analiz et:
1. Vimshottari Dasha ana dönemi — yaşamın büyük döngüsü
2. Firdaria kronokrator değişimleri — yıllık yönetici etkileri
3. Büyük gezegen transitleri (Jüpiter döngüsü, Satürn döngüsü)
4. Solar Return yıllık haritalarının kümülatif etkisi
5. Deep harmonic uzun dalga analizi
6. Kariyer, ilişki, sağlık, finans ve spiritüel gelişim başlıklarında uzun vadeli yol haritası
""",
        "career": """
## KARİYER ANALİZİ
Yukarıdaki verileri kullanarak kariyer ve mesleki potansiyeli analiz et:
1. MC (Tepe Noktası) ve 10. ev yerleşimleri — kariyer yönü
2. Satürn ve Jüpiter konumları — profesyonel disiplin ve şans
3. 6. ev (günlük çalışma) ve 2. ev (gelir) vurguları
4. Sabit yıldızların kariyer etkileri (Spica, Regulus, Sirius vb.)
5. Solar Return kariyer ev vurguları
6. Firdaria profesyonel dönem döngüleri
7. Arap noktalarından meslek ve başarı göstergeleri
8. Transit etkilerle kariyer fırsat pencereleri
""",
        "health": """
## SAĞLIK ANALİZİ
Yukarıdaki verileri kullanarak sağlık ve bedensel potansiyeli analiz et:
1. 6. ev (sağlık) ve 1. ev (beden) yerleşimleri
2. Mars enerjisi ve fiziksel dayanıklılık
3. Satürn kronik eğilimleri ve zayıf bölgeler
4. Sabit yıldızların sağlık etkileri (Algol, Caput Algol vb.)
5. Deklinasyon paralellerinde sağlık göstergeleri
6. Solar Return sağlık ev vurguları
7. Transit etkilerle sağlık uyarıları ve olumlu dönemler
""",
        "finance": """
## FİNANSAL ANALİZ
Yukarıdaki verileri kullanarak finansal potansiyeli ve para yönetimini analiz et:
1. 2. ev (gelir) ve 8. ev (ortak kaynaklar) yerleşimleri
2. Jüpiter ve Venüs'ün finansal etkileri — bolluk ve kaynak akışı
3. Part of Fortune (Şans Noktası) ve Arap finans noktaları
4. Gezegen dignity skorlarına göre kaynak yönetimi gücü
5. Solar Return finansal ev vurguları
6. Transit Jüpiter ve Satürn'ün 2. ve 8. evden geçişleri
7. Finansal fırsat pencereleri ve riskli dönemler
""",
        "spiritual": """
## RUHSAL GELİŞİM ANALİZİ
Yukarıdaki verileri kullanarak spiritüel potansiyeli ve ruhsal yolculuğu analiz et:
1. 9. ev (yüksek bilinç), 12. ev (spiritüel derinlik), Neptün yerleşimi
2. Deep harmonic (H5, H7, H9, H12) — spiritüel titreşim katmanları
3. Vimshottari Dasha spiritüel dönemi — içsel yolculuk zamanlaması
4. Navamsa (H9) haritasından ruhsal eğilimler
5. Ay düğümleri — kadersel ruhsal misyon
6. Ay fazı (lunation cycle) — spiritüel ritim
7. Sabit yıldızların spiritüel etkileri (Fomalhaut, Aldebaran vb.)
8. Antiscia noktaları — gölge ve denge dinamikleri
""",
        "summary": """
## KOZMİK ÖZET (KISA)
Yukarıdaki verileri kullanarak 300-500 kelimelik kısa ve öz bir kozmik özet hazırla:
1. En güçlü 3 gezegen ve hayata etkisi
2. Yaşam amacı ve potansiyel
3. Şu anki transit dönemin ana mesajı
4. Önümüzdeki dönem için en önemli tek tavsiye
KISA olsun, uzun yazma. Her başlık 2-3 cümle yeterli.
""",
    }

    # Provider ayarlarını cache'le
    _providers_cache = None
    _fallback_order = []
    _last_fetch = 0
    CACHE_TTL = 60  # saniye

    def __init__(self):
        self.sync_client = None
        # Fallback: env'den oku (Firestore yoksa)
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self.sync_client = OpenAI(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1"
            )

    def _get_providers_from_firestore(self) -> dict:
        """Firestore'dan AI ayarlarını getir (cache'li)"""
        now = datetime.now().timestamp()
        if self._providers_cache and (now - self._last_fetch) < self.CACHE_TTL:
            return self._providers_cache

        try:
            from services.firebase_service import firebase_service
            db = firebase_service.db
            if db:
                doc = db.collection('config').document('ai_settings').get()
                if doc.exists:
                    data = doc.to_dict()
                    self._providers_cache = data
                    self._last_fetch = now
                    logger.info(f"[AI] Ayarlar Firestore'dan yüklendi. Provider: {len(data.get('providers', []))} adet")
                    return data
        except Exception as e:
            logger.error(f"[AI] Firestore okuma hatası (önemsiz, env fallback): {e}")

        return {}

    def _get_provider_by_name(self, name: str, providers: list) -> Optional[dict]:
        """Provider adına göre provider bilgisini bul"""
        if not name or not providers:
            return None
        for p in providers:
            if p.get('name') == name:
                return p
        return None

    def _get_fallback_chain(self) -> List[dict]:
        """Aktif + yedek sırasına göre provider listesi döndür"""
        settings = self._get_providers_from_firestore()
        providers = settings.get('providers', [])

        if not providers:
            # Firestore'da provider yoksa env'den dene
            return self._get_env_fallback_chain()

        chain = []
        order_keys = ['active_provider', 'backup_1', 'backup_2', 'backup_3']

        for key in order_keys:
            name = settings.get(key, '')
            provider = self._get_provider_by_name(name, providers)
            if provider:
                chain.append(provider)

        # Eğer hiç provider yoksa env'den dene
        if not chain:
            return self._get_env_fallback_chain()

        logger.info(f"[AI] Fallback zinciri: {' -> '.join(p['name'] for p in chain)}")
        return chain

    def _get_env_fallback_chain(self) -> List[dict]:
        """Ortam değişkenlerinden provider bilgilerini oku (eski sistem)"""
        chain = []
        if os.getenv("DEEPSEEK_API_KEY"):
            chain.append({
                "name": "DeepSeek (env)",
                "base_url": "https://api.deepseek.com",
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "model": "deepseek-chat",
            })
        if os.getenv("ZAI_API_KEY"):
            chain.append({
                "name": "ZAI (env)",
                "base_url": "https://api.zai-api.com/v1",
                "api_key": os.getenv("ZAI_API_KEY"),
                "model": "zai-chat",
            })
        if os.getenv("OPENROUTER_API_KEY"):
            chain.append({
                "name": "OpenRouter (env)",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY"),
                "model": "openrouter/auto",
            })
        return chain

    @staticmethod
    def remove_emojis(text: str) -> str:
        emoji_pattern = re.compile(
            "[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f700-\U0001f77f"
            "\U0001f780-\U0001f7ff\U0001f800-\U0001f8ff\U0001f900-\U0001f9ff\U0001fa00-\U0001fa6f"
            "\U0001fa70-\U0001faff\U00002702-\U000027b0\U000024c2-\U0001f251\U0001f1e0-\U0001f1ff"
            "\U00002600-\U000026ff\U00002700-\U000027bf\U0000fe00-\U0000fe0f\U0001f000-\U0001f02f"
            "\U0001f0a0-\U0001f0ff]+",
            flags=re.UNICODE,
        )
        cleaned = emoji_pattern.sub("", text)
        cleaned = re.sub(r" +", " ", cleaned)
        return "\n".join(line.strip() for line in cleaned.split("\n")).strip()

    async def call_provider(self, session: aiohttp.ClientSession, provider: dict, prompt: str, interpretation_type: str = "") -> dict:
        """Tek bir provider'a API çağrısı yap"""
        base_url = provider['base_url'].rstrip('/')
        api_key = provider['api_key']
        model = provider.get('model', 'deepseek-chat')
        name = provider.get('name', 'Bilinmeyen')

        # OpenAI uyumlu API endpoint
        url = f"{base_url}/chat/completions" if not base_url.endswith('/chat/completions') else base_url

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Sen dünyanın en iyi astroloğusun."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 32768,
            "stream": False,  # Streaming kapat — 502/reset hatasını önler
        }

        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    # Token limitinden dolayi kesilme kontrolu
                    finish_reason = data["choices"][0].get("finish_reason", "stop")
                    if finish_reason == "length":
                        logger.warning(f"[AI] ⚠️ {name} max_tokens'e ulasti, yanit kesilmis olabilir")
                    # content None olabilir (API hatasi veya bos yanit)
                    content_len = len(content) if content else 0
                    if not content:
                        logger.warning(f"[AI] ❌ {name} boş yanit döndü (finish_reason={finish_reason})")
                        return {"success": False, "error": f"{name}: boş yanit", "provider": name}
                    logger.info(f"[AI] ✅ {name} başarılı (finish_reason={finish_reason}, len={content_len})")
                    return {"success": True, "interpretation": self.remove_emojis(content), "provider": name}
                else:
                    error_text = await resp.text()
                    logger.warning(f"[AI] ❌ {name} hata {resp.status}: {error_text[:200]}")
                    return {"success": False, "error": f"{name}: HTTP {resp.status}", "provider": name}
        except asyncio.TimeoutError:
            logger.warning(f"[AI] ⏰ {name} timeout (90sn)")
            return {"success": False, "error": f"{name}: timeout", "provider": name}
        except Exception as e:
            logger.warning(f"[AI] ❌ {name} exception: {str(e)[:100]}")
            return {"success": False, "error": f"{name}: {str(e)[:100]}", "provider": name}

    def _filter_astro_data(self, astro_data: dict, analysis_type: str) -> dict:
        """Her analiz türü için sadece gerekli hesaplama sonuçlarını filtrele.
        Eşleşme yoksa tüm veriyi döndür (geriye dönük uyumlu)."""
        if not astro_data or not isinstance(astro_data, dict):
            logger.warning(f"[AI] astro_data None veya geçersiz, boş dict dönülüyor.")
            return {}
        allowed_keys = self.DATA_FILTER.get(analysis_type)
        if not allowed_keys:
            logger.warning(f"[AI] {analysis_type} için filtre tanımı yok, tüm veri gönderiliyor.")
            return astro_data
        filtered = {}
        skipped_count = 0
        for key in allowed_keys:
            if key in astro_data:
                filtered[key] = astro_data[key]
        # Hangi hesaplamalar atlandı logla
        skipped = [k for k in astro_data if k not in allowed_keys]
        if skipped:
            logger.info(f"[AI] Filtre '{analysis_type}': {len(filtered)}/{len(astro_data)} key gönderildi, {len(skipped)} atlandı: {skipped}")
        else:
            logger.info(f"[AI] Filtre '{analysis_type}': Tüm {len(filtered)} key gönderildi.")
        return filtered

    # Sadece major açılar: Conjunction, Opposition, Square, Trine, Sextile
    MAJOR_ASPECTS = {"Conjunction", "Opposition", "Square", "Trine", "Sextile"}
    # Sadece ana gezegenler + önemli noktalar arası açılar (asteroid ve uranyenler yok)
    IMPORTANT_BODIES = {
        "Sun", "Moon", "Mercury", "Venus", "Mars",
        "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
        "Ascendant", "MC", "Armc", "True_Node",
    }

    @staticmethod
    def _is_important_aspect(item: dict) -> bool:
        """Sadece ana gezegenler/noktalar arası major açılar, orb < 8"""
        p1 = item.get("planet1", "")
        p2 = item.get("planet2", "")
        aspect = item.get("aspect_type", "")
        orb = abs(float(item.get("orb", 99)))
        # Major aspect kontrol
        if aspect not in AIService.MAJOR_ASPECTS:
            return False
        # İki taraf da önemli cisimlerden olmalı
        if p1 not in AIService.IMPORTANT_BODIES or p2 not in AIService.IMPORTANT_BODIES:
            return False
        # Orb sınırı (Conjunction/Opposition: 8, Square/Trine: 7, Sextile: 5)
        if aspect == "Sextile" and orb > 5:
            return False
        if orb > 8:
            return False
        return True

    @staticmethod
    def _deep_trim(data: dict, max_items: int = 30) -> dict:
        """Büyük dizileri derinlemesine kırp: sadece önemli major açılar, en dar orb'lular."""
        trimmed = {}
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 10:
                # Açı listeleri: sadece önemli major açılar → orb sıralı
                if all(isinstance(item, dict) and "aspect_type" in item for item in value[:3]):
                    filtered = [item for item in value if AIService._is_important_aspect(item)]
                    filtered.sort(key=lambda x: abs(float(x.get("orb", 99))))
                    trimmed[key] = filtered[:max_items]
                    logger.info(f"[AI] Deep trim '{key}': {len(value)} → {len(filtered[:max_items])} (önemli major açılar)")

                # Sabit yıldızlar: top 10
                elif all(isinstance(item, dict) and ("star" in str(item).lower() or "name" in item) for item in value[:3]):
                    trimmed[key] = value[:10]
                    logger.info(f"[AI] Deep trim '{key}': {len(value)} → {len(value[:10])} (top 10)")

                # Midpoint / genel dizi: top 10
                elif all(isinstance(item, dict) for item in value[:3]):
                    trimmed[key] = value[:10]
                    logger.info(f"[AI] Deep trim '{key}': {len(value)} → {len(value[:10])} (top 10)")

                else:
                    trimmed[key] = value
            elif isinstance(value, dict):
                trimmed[key] = AIService._deep_trim(value, max_items)
            else:
                trimmed[key] = value
        return trimmed

    async def get_ai_interpretation_async(self, astro_data: dict, interpretation_type: str, user_name: str, **kwargs) -> dict:
        """Sıralı yedekleme ile AI yorumu al — analiz türüne özel veri + prompt"""
        # Veriyi filtrele
        filtered_data = self._filter_astro_data(astro_data, interpretation_type)
        # Derinlemesine kırp: major açılar, top N
        filtered_data = self._deep_trim(filtered_data)
        data_json = json.dumps(filtered_data, default=str)
        data_size = len(data_json)
        logger.info(f"[AI] Prompt data boyutu: {data_size:,} bytes (~{data_size//4:,} token)")

        # Analiz türüne özel prompt veya genel prompt
        type_prompt = self.TYPE_PROMPTS.get(interpretation_type)
        if type_prompt:
            prompt = f"User: {user_name}\n{type_prompt}\nData: {data_json}\n{self.BASE_RULES}"
        else:
            prompt = f"User: {user_name}\nType: {interpretation_type}\nData: {data_json}\n{self.BASE_RULES}"

        extra = {k: v for k, v in kwargs.items() if v}
        if extra:
            prompt += f"\nExtra: {json.dumps(extra, default=str)}"

        fallback_chain = self._get_fallback_chain()

        if not fallback_chain:
            return {"success": False, "error": "Hiçbir AI provider yapılandırılmamış"}

        errors = []
        async with aiohttp.ClientSession() as session:
            for i, provider in enumerate(fallback_chain):
                tag = "AKTİF" if i == 0 else f"YEDEK-{i}"
                logger.info(f"[AI] Deneniyor: {tag} -> {provider['name']}")
                result = await self.call_provider(session, provider, prompt, interpretation_type)
                if result["success"]:
                    return result
                errors.append(result.get("error", "Bilinmeyen hata"))

        logger.error(f"[AI] Tüm provider'lar başarısız: {' | '.join(errors)}")
        return {"success": False, "error": f"Tüm AI sağlayıcıları başarısız: {'; '.join(errors)}"}

    def get_ai_interpretation(self, astro_data: dict, interpretation_type: str, user_name: str, **kwargs) -> dict:
        """Senkron wrapper"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.get_ai_interpretation_async(astro_data, interpretation_type, user_name, **kwargs)
        )


ai_service = AIService()


def get_ai_interpretation_engine(astro_data, interpretation_type, user_name, **kwargs):
    return ai_service.get_ai_interpretation(astro_data, interpretation_type, user_name, **kwargs)
