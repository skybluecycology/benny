import asyncio
import httpx
import json

async def probe_lemonade():
    endpoints = [
        "http://127.0.0.1:13305/api/v1/chat/completions",
        "http://127.0.0.1:13305/v1/chat/completions",
        "http://127.0.0.1:13305/chat/completions",
    ]
    
    payload = {
        "model": "deepseek-r1-8b-FLM",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5
    }
    
    print("--- Lemonade Endpoint Discovery ---")
    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in endpoints:
            print(f"Checking: {url}")
            try:
                resp = await client.post(url, json=payload)
                print(f"  Status: {resp.status_code}")
                if resp.status_code == 200:
                    print(f"  SUCCESS! Response: {resp.json()['choices'][0]['message']['content']}")
                    return url
                else:
                    print(f"  Error body: {resp.text[:100]}")
            except Exception as e:
                print(f"  Connection failed: {e}")
    return None

if __name__ == "__main__":
    asyncio.run(probe_lemonade())
