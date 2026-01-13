import os
import json
import time
import threading
import asyncio
import ssl
from aiohttp import web
from websocket import WebSocketApp

# --- KONFIGURASI ---
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "cb1af94b-28f0-4d76-b827-37c4df023c2c")
DEVICE_ID = os.environ.get("DEVICE_ID", "c47bb81b535832546db3f7f016eb01a0")
ASSET = "Z-CRY/IDX"

# --- DEBUG: CEK TOKEN APA YANG DIPAKAI ---
print(f"---------------------------------------------------")
print(f"SYSTEM MULAI...")
print(f"TOKEN YANG SEDANG DIGUNAKAN: {AUTH_TOKEN[:15]}...")
print(f"---------------------------------------------------")

class ZiroFinalEngine:
    def __init__(self):
        self.clients = set()
        self.loop = None
        self.last_price = 0
        self.rsi = 50.0
        self.history = []

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            for client in list(self.clients):
                try:
                    await client.send_str(msg)
                except:
                    self.clients.remove(client)

    def on_message(self, ws, message):
        try:
            # Kita matikan print raw data agar bersih
            data = json.loads(message)

            if "data" in data and data["data"]:
                for item in data["data"]:
                    assets = item.get("assets", [])
                    for asset in assets:
                        if asset.get("ric") == ASSET:
                            try:
                                price = float(asset["rate"])
                                self.last_price = price
                                
                                self.history.append(price)
                                if len(self.history) > 14: self.history.pop(0)
                                if len(self.history) >= 14:
                                    gains = sum(max(self.history[i]-self.history[i-1], 0) for i in range(1, len(self.history)))
                                    losses = sum(max(self.history[i-1]-self.history[i], 0) for i in range(1, len(self.history)))
                                    if losses > 0:
                                        rs = gains / losses
                                        self.rsi = 100 - (100 / (1 + rs))
                                    else:
                                        self.rsi = 100.0 if gains > 0 else 50.0

                                packet = {
                                    "price": self.last_price,
                                    "rsi": round(self.rsi, 2),
                                    "timestamp": time.time()
                                }

                                if self.loop:
                                    asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
                                    
                                print(f">> UPDATE: {price} | RSI: {round(self.rsi, 2)}")

                            except ValueError:
                                pass 
        except Exception as e:
            print(f">> Error parsing: {e}")

    def on_open(self, ws):
        print(">> TERHUBUNG KE STOCKITY STREAM")
        ws.send(json.dumps({"action": "subscribe", "rics": [ASSET]}))
        ws.send(json.dumps({"event": "subscribe", "topic": f"asset:{ASSET}"}))

    def on_error(self, ws, error):
        print(f">> ERROR KONEKSI: {error}")
        if "401" in str(error):
            print("!! PERINGATAN: TOKEN DITOLAK (401) !!")

    def on_close(self, ws, close_status_code, close_msg):
        print(">> TERPUTUS. REKONEKSI 5 DETIK...")

    def start_ws(self):
        url = "wss://as.stockitymob.com/"
        while True:
            try:
                ws = WebSocketApp(
                    url,
                    header={
                        "authorization-token": AUTH_TOKEN, 
                        "device-id": DEVICE_ID,
                        "device-type": "web",
                        "User-Agent": "Mozilla/5.0"
                    },
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
            except Exception as e:
                print(f">> Critical Error: {e}")
            time.sleep(5)

engine = ZiroFinalEngine()

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    engine.clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                pass
    finally:
        engine.clients.remove(ws)
    return ws

async def index_page(request):
    return web.FileResponse('index.html')

async def dash_page(request):
    return web.FileResponse('web.html')

app = web.Application()
app.router.add_get('/', index_page)
app.router.add_get('/web.html', dash_page)
app.router.add_get('/ws', handle_ws)

if __name__ == "__main__":
    engine.loop = asyncio.get_event_loop()
    threading.Thread(target=engine.start_ws, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, port=port)
