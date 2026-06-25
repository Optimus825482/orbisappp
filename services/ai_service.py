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

    async def call_provider(self, session: aiohttp.ClientSession, provider: dict, prompt: str) -> dict:
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
            "max_tokens": 4096,  # Uzun analizler yarim kesilmesin
        }

        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    # Token limitinden dolayi kesilme kontrolu
                    finish_reason = data["choices"][0].get("finish_reason", "stop")
                    if finish_reason == "length":
                        logger.warning(f"[AI] ⚠️ {name} max_tokens'e ulasti, yanit kesilmis olabilir")
                    logger.info(f"[AI] ✅ {name} başarılı (finish_reason={finish_reason}, len={len(content)})")
                    return {"success": True, "interpretation": self.remove_emojis(content), "provider": name}
                else:
                    error_text = await resp.text()
                    logger.warning(f"[AI] ❌ {name} hata {resp.status}: {error_text[:200]}")
                    return {"success": False, "error": f"{name}: HTTP {resp.status}", "provider": name}
        except asyncio.TimeoutError:
            logger.warning(f"[AI] ⏰ {name} timeout (60sn)")
            return {"success": False, "error": f"{name}: timeout", "provider": name}
        except Exception as e:
            logger.warning(f"[AI] ❌ {name} exception: {str(e)[:100]}")
            return {"success": False, "error": f"{name}: {str(e)[:100]}", "provider": name}

    async def get_ai_interpretation_async(self, astro_data: dict, interpretation_type: str, user_name: str, **kwargs) -> dict:
        """Sıralı yedekleme ile AI yorumu al"""
        prompt = f"User: {user_name}\nType: {interpretation_type}\nData: {json.dumps(astro_data, default=str)}\n{self.BASE_RULES}"
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
                result = await self.call_provider(session, provider, prompt)
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
