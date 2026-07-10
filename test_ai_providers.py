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

async def test_one(session, p, prompt, timeout=30):
    url = p["base_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    payload = dict(model=p["model"], messages=[dict(role="user", content=prompt)],
                   max_tokens=256, temperature=0.3, stream=False)
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
    prompt = "1+1? One word." if prompt_type == "simple" else "Introduce yourself in 3 sentences."
    print("\n=== AI PROVIDER TEST (%d providers) ===" % len(providers))
    print("Prompt: %s" % prompt)
    print("%-25s %-20s %8s %8s" % ("Provider", "Model", "Result", "Time"))
    print("-" * 70)
    async with aiohttp.ClientSession() as session:
        for p in providers:
            tag = "*" if p.get("active") else " "
            label = "[%s] %-22s %-20s " % (tag, p["name"][:22], p["model"][:20])
            print(label, end="", flush=True)
            ok, elapsed, content, err = await test_one(session, p, prompt, timeout=30)
            if ok:
                print("OK   %6.1fs" % elapsed)
            else:
                print("FAIL %6.1fs  %s" % (elapsed, err[:80]))
    print("=" * 70)

if __name__ == "__main__":
    pt = sys.argv[1] if len(sys.argv) > 1 else "simple"
    asyncio.run(main(pt))
