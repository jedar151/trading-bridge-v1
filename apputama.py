import json
import time
import ssl
import os
import asyncio
import threading
import statistics
from datetime import datetime
from aiohttp import web

# --- KONFIGURASI ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Infinix X6531B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"

BRIDGE_CLIENTS = set()

class PhoenixProvider:
    def __init__(self, loop):
        self.loop = loop
        self.token = AUTH_TOKEN
        self.price_history = []
        self.server_time_offset = 0

    async def broadcast(self, data):
        if not BRIDGE_CLIENTS: return
        payload = json.dumps(data)
        for ws in list(BRIDGE_CLIENTS):
            try:
                await ws.send_str(payload)
            except:
                BRIDGE_CLIENTS.remove(ws)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and len(data["data"]) > 0:
                asset = data["data"][0]["assets"][0]
                if asset.get("ric") == "Z-CRY/IDX":
                    price = float(asset["rate"])
                    self.price_history.append(price)
                    if len(self.price_history) > 50: self.price_history.pop(0)
                    
                    # Hitung detik ke depan (Countdown)
                    server_ts = time.time() + self.server_time_offset
                    countdown = ((int(server_ts // 60) + 1) * 60) - server_ts

                    packet = {
                        "price": price,
                        "rsi": 50.0, # Sederhana dulu
                        "countdown": countdown,
                        "call_pct": 50, "put_pct": 50
                    }
                    asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        except: pass

    def start(self):
        from websocket import WebSocketApp
        def run():
            while True:
                try:
                    ws = WebSocketApp("wss://as.stockitymob.com/",
                        header={"authorization-token": self.token, "device-id": DEVICE_ID, "User-Agent": USER_AGENT},
                        on_message=self.on_message)
                    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                except: time.sleep(5)
        threading.Thread(target=run, daemon=True).start()

# --- HANDLER UNTUK RENDER ---
async def handle_index(request):
    # Ini yang akan memanggil file index.html Anda
    return web.FileResponse('./index.html')

async def handle_ws(request):
    # Ini jalur pipa data untuk dashboard
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        BRIDGE_CLIENTS.remove(ws)
    return ws

async def main():
    loop = asyncio.get_running_loop()
    bot = PhoenixProvider(loop)
    bot.start()

    app = web.Application()
    app.router.add_get('/', handle_index)  # Menampilkan tampilan utama
    app.router.add_get('/ws', handle_ws)   # Jalur data live
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
