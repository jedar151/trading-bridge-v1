import json
import os
import asyncio
import random
from aiohttp import web

# --- SIMULATOR MODE ---
# Kode ini akan mengirim data acak setiap 1 detik untuk ngetes tampilan
BRIDGE_CLIENTS = set()

async def broadcast_fake_data():
    """Fungsi untuk mengirim data palsu agar dashboard bergerak"""
    price = 10420.00
    while True:
        if BRIDGE_CLIENTS:
            price += random.uniform(-1.0, 1.0)
            data = {
                "price": round(price, 2),
                "rsi": random.randint(30, 70),
                "countdown": random.randint(1, 60),
                "call_pct": random.randint(40, 60),
                "put_pct": random.randint(40, 60)
            }
            payload = json.dumps(data)
            for ws in list(BRIDGE_CLIENTS):
                try:
                    await ws.send_str(payload)
                except:
                    BRIDGE_CLIENTS.remove(ws)
        await asyncio.sleep(1)

async def handle_index(request):
    return web.FileResponse('./index.html')

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        BRIDGE_CLIENTS.remove(ws)
    return ws

async def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/ws', handle_ws)
    
    # Jalankan simulator di background
    asyncio.create_task(broadcast_fake_data())
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    print(f"Simulator aktif di port {port}")
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
