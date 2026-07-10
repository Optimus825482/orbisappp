"""
AI Provider Benchmark - Her provider'a gerÁek prompt ile test, s¸re ˆlÁer.
Admin panelden tetiklenebilir, veya manuel: python test_ai_providers.py
"""
import asyncio, aiohttp, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def get_providers():
    """Firestore'dan veya env'den provider listesini al"""
    providers = []
    try:
        from services.firebase_service import firebase_service
        db = firebase_service.db
        if db:
            doc = db.collection('config').document('ai_settings').get()
            if doc.exists:
                data = doc.to_dict()
                provs = data.get('providers', [])
                active = data.get('active_provider', '')
                for p in provs:
                    providers.append({
                        'name': p.get('name', '?'),
                        'base_url': p.get('base_url', ''),
                        'api_key': p.get('api_key', ''),
                        'model': p.get('model', ''),
                        'active': p.get('name') == active,
                    })
    except Exception as e:
        print(f"[WARN] Firestore okunamadi: {e}")

    if not providers:
        print("[INFO] Firestore bos, env fallback deneniyor...")
        if os.getenv("DEEPSEEK_API_KEY"):
            providers.append({'name': 'DEEPSEEK(env)', 'base_url': 'https://api.deepseek.com', 'api_key': os.getenv("DEEPSEEK_API_KEY"), 'model': 'deepseek-chat', 'active': True})
        if os.getenv("OPENROUTER_API_KEY"):
            providers.append({'name': 'OPENROUTER(env)', 'base_url': 'https://openrouter.ai/api/v1', 'api_key': os.getenv("OPENROUTER_API_KEY"), 'model': 'openrouter/auto', 'active': False})
    return providers

async def test_one(session, p, prompt, timeout=60):
    """Tek provider test. (ba˛ari, s¸re_sn, yanit_ilk_100, hata)"""
    url = p['base_url'].rstrip('/')
    if not url.endswith('/chat/completions'):
        url += '/chat/completions'

    payload = {
        "model": p['model'],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.3,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {p['api_key']}", "Content-Type": "application/json"}
    start = time.time()
    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            elapsed = time.time() - start
            raw = await resp.text()
            if resp.status == 200:
                try:
                    data = json.loads(raw)
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')[:200]
                    return (True, elapsed, content, None)
                except:
                    return (True, elapsed, raw[:200], f"JSON parse hatasi")
            else:
                return (False, elapsed, '', f"HTTP {resp.status}: {raw[:200]}")
    except asyncio.TimeoutError:
        return (False, timeout, '', f"TIMEOUT ({timeout}s)")
    except Exception as e:
        return (False, time.time() - start, '', str(e)[:200])

async def main(prompt_type="simple"):
    providers = get_providers()
    if not providers:
        print("‚ùå Provider bulunamadi!")
        return

    prompt = "1+1 kac eder? Tek kelime cevap ver." if prompt_type == "simple" else "Merhaba, kendini tanitir misin? 3 cumle."

    print(f"\n{'='*70}")
    print(f"AI PROVIDER BENCHMARK - {len(providers)} provider")
    print(f"Prompt: {prompt[:80]}...")
    print(f"{'='*70}")
    print(f"{'Provider':<25} {'Model':<20} {'Sonuc':>8} {'Sure':>8}")
    print(f"{'-'*70}")

    async with aiohttp.ClientSession() as session:
        for p in providers:
            tag = "‚òÖ" if p.get('active') else " "
            print(f"[{tag}] {p['name']:<22} {p['model']:<20} ", end="", flush=True)
            ok, elapsed, content, err = await test_one(session, p, prompt, timeout=30)
            if ok:
                print(f"‚úÖ OK   {elapsed:>6.1f}s")
            else:
                print(f"‚ùå FAIL {elapsed:>6.1f}s  {err[:80]}")

    print(f"{'='*70}")
    print("Done.")

if __name__ == "__main__":
    prompt_type = sys.argv[1] if len(sys.argv) > 1 else "simple"
    asyncio.run(main(prompt_type))
