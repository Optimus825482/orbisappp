# -*- coding: utf-8 -*-
"""AI Provider Benchmark"""
import asyncio, aiohttp, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def get_providers():
    providers = []
    try:
        from services.firebase_service import firebase_service
        db = firebase_service.db
        if db:
            doc = db.collection("config").document("ai_settings").get()
            if doc.exists:
                data = doc.to_dict()
                provs = data.get("providers", [])
                active = data.get("active_provider", "")
                for p in provs:
                    providers.append(dict(
                        name=p.get("name","?"),
                        base_url=p.get("base_url",""),
                        api_key=p.get("api_key",""),
                        model=p.get("model",""),
                        active=(p.get("name") == active),
                    ))
    except Exception as e:
        print("[WARN] Firestore: %s" % e)
    if not providers:
        print("[INFO] env fallback")
        if os.getenv("DEEPSEEK_API_KEY"):
            providers.append(dict(name="DEEPSEEK(env)", base_url="https://api.deepseek.com",
                                  api_key=os.getenv("DEEPSEEK_API_KEY"), model="deepseek-chat", active=True))
    return providers

async def test_one(session, p, prompt, max_tokens=256, timeout=30):
    url = p["base_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    payload = dict(model=p["model"], messages=[dict(role="user", content=prompt)],
                   max_tokens=max_tokens, temperature=0.3)
    headers = {"Authorization": "Bearer " + p["api_key"], "Content-Type": "application/json"}
    start = time.time()
    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            elapsed = time.time() - start
            raw = await resp.text()
            if resp.status == 200:
                try:
                    data = json.loads(raw)
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")[:200]
                    return (True, elapsed, content, None)
                except:
                    return (True, elapsed, raw[:200], "JSON parse error")
            else:
                return (False, elapsed, "", "HTTP %d: %s" % (resp.status, raw[:200]))
    except asyncio.TimeoutError:
        return (False, timeout, "", "TIMEOUT")
    except Exception as e:
        return (False, time.time() - start, "", str(e)[:200])

async def main(prompt_type="simple"):
    providers = get_providers()
    if not providers:
        print("No providers!")
        return

    if prompt_type == "real":
        # GERCEK astro prompt — uygulamanin gonderdigiyle ayni
        import random
        astro_json = json.dumps({
            "natal_planet_positions": {"Sun":{"sign":"Ikizler","house":10,"degree":80.14},"Moon":{"sign":"Kova","house":5,"degree":311.72},"Mercury":{"sign":"Ikizler","house":9,"retrograde":True},"Venus":{"sign":"Boga","house":9},"Mars":{"sign":"Terazi","house":1},"Jupiter":{"sign":"Akrep","house":2,"retrograde":True},"Saturn":{"sign":"Terazi","house":2,"retrograde":True},"Ascendant":{"sign":"Basak","degree":168.12},"MC":{"sign":"Ikizler","degree":76.21}},
            "natal_houses": {"house_cusps":{"1":168,"2":193,"3":223,"4":256,"5":290,"6":321,"7":348,"8":13,"9":43,"10":76,"11":110,"12":141}},
            "natal_ascendant": {"sign":"Basak","degree":168.12},
            "natal_aspects": [{"planet1":"Sun","planet2":"Ascendant","aspect_type":"Square","orb":2.0},{"planet1":"Moon","planet2":"Saturn","aspect_type":"Trine","orb":3.8},{"planet1":"Mars","planet2":"Mercury","aspect_type":"Trine","orb":1.3},{"planet1":"Venus","planet2":"Moon","aspect_type":"Square","orb":1.7},{"planet1":"Saturn","planet2":"Sun","aspect_type":"Trine","orb":4.6}],
            "natal_additional_points": {"True_Node":{"sign":"Yengec","house":10},"Chiron":{"sign":"Boga"},"True_Lilith":{"sign":"Oglak","house":4}},
        })
        prompt = "User: ERKAN ERDEM\n## DOĞUM HARİTASI VE KARAKTER ANALİZİ\nYukarıdaki verileri kullanarak kapsamlı bir doğum haritası analizi yap.\nŞu başlıkları detaylıca işle:\n1. Yükselen burcun kişiliğe etkisi\n2. Ay burcunun duygusal yapıya etkisi\n3. Güneş burcunun temel karaktere etkisi\n4. Gezegenlerin ev yerleşimleri\n5. Önemli açılar ve kişilik dinamikleri\n\nData: %s\n\n## KESİN KURALLAR\n### 1. YASAK TERİMLER (ASLA KULLANMA)\n- Gezegen isimleri, burç isimleri, ev numaraları, açı isimleri, teknik terimler\n### 2. DİL VE ÜSLUP\n- Sade, anlaşılır Türkçe\n- Doğrudan ve net ifadeler\n### 3. UZUNLUK (ÖNEMLİ)\n- Yanitin en az 1500 kelime olsun" % astro_json
        max_tok = 32768
        timeout = 120
    elif prompt_type == "astro":
        prompt = "Introduce yourself in 3 sentences."
        max_tok = 256
        timeout = 30
    else:
        prompt = "1+1? One word."
        max_tok = 256
        timeout = 30

    print("\n=== AI PROVIDER TEST (%d providers) ===" % len(providers))
    print("Mode: %s | max_tokens=%d | timeout=%ds" % (prompt_type, max_tok, timeout))
    print("Prompt size: %d bytes" % len(prompt))
    print("%-25s %-20s %8s %8s %s" % ("Provider", "Model", "Result", "Time", "Tokens"))
    print("-" * 85)
    async with aiohttp.ClientSession() as session:
        for p in providers:
            tag = "*" if p.get("active") else " "
            label = "[%s] %-22s %-20s " % (tag, p["name"][:22], p["model"][:20])
            print(label, end="", flush=True)
            ok, elapsed, content, err = await test_one(session, p, prompt, max_tok, timeout)
            tok_est = len(content) // 4 if ok else 0
            if ok:
                print("OK   %6.1fs  ~%dtok" % (elapsed, tok_est))
            else:
                print("FAIL %6.1fs  %s" % (elapsed, err[:80]))
    print("=" * 85)

if __name__ == "__main__":
    pt = sys.argv[1] if len(sys.argv) > 1 else "simple"
    asyncio.run(main(pt))
