import os
import json
import time
import ssl
import statistics
import asyncio
import threading
from datetime import datetime
from aiohttp import web
import websocket

# --- KONFIGURASI DARI TERMUX PROFESOR ---
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Infinix X6531B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
ASSET = "Z-CRY/IDX"

class PhoenixRenderBridge:
    def __init__(self):
        self.clients = set()
        self.price_history = []
        self.max_history = 50
        self.last_price = 0.0
        self.current_rsi = 50.0
        self.server_time_offset = 0
        self.majority_call_pct = 50.0
        self.majority_put_pct = 50.0
        self.loop = None

    def calculate_rsi(self, period=14):
        if len(self.price_history) < period + 1: return 50.0
        prices = self.price_history[-period:]
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff > 0: gains.append(diff); losses.append(0)
            else: gains.append(0); losses.append(abs(diff))
        avg_gain = statistics.mean(gains) if gains else 0
        avg_loss = statistics.mean(losses) if losses else 0
        if avg_loss == 0: return 100.0
        return 100 - (100 / (1 + (avg_gain / avg_loss)))

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            for client in list(self.clients):
                try: await client.send_str(msg)
                except: self.clients.remove(client)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            # 1. Opini Mayoritas
            if data.get("event") == "majority_opinion":
                p = data.get("payload", {})
                total = p.get("call", 0) + p.get("put", 0)
                if total > 0:
                    self.majority_call_pct = (p["call"] / total) * 100
                    self.majority_put_pct = (p["put"] / total) * 100

            # 2. Update Harga (Format Termux)
            elif "data" in data and len(data["data"]) > 0:
                item = data["data"][0]
                if "assets" in item:
                    asset = item["assets"][0]
                    if asset.get("ric") == ASSET:
                        self.last_price = float(asset["rate"])
                        self.price_history.append(self.last_price)
                        if len(self.price_history) > self.max_history: self.price_history.pop(0)
                        
                        self.current_rsi = self.calculate_rsi()
                        
                        # Hitung Countdown
                        if "provider_time" in asset:
                            server_dt = datetime.fromisoformat(asset["provider_time"].replace('Z', '+00:00'))
                            self.server_time_offset = server_dt.timestamp() - time.time()
                        
                        server_ts = time.time() + self.server_time_offset
                        countdown = ((int(server_ts // 60) + 1) * 60) - server_ts

                        # Kirim ke Browser
                        if self.loop:
                            packet = {
                                "type": "tick",
                                "price": self.last_price,
                                "rsi": self.current_rsi,
                                "call_pct": self.majority_call_pct,
                                "put_pct": self.majority_put_pct,
                                "countdown": countdown
                            }
                            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self.broadcast(packet)))
        except: pass

    def on_open(self, ws):
        print(">> CONNECTED TO STOCKITY (PHOENIX LOGIC)")
        ws.send(json.dumps({"action": "subscribe", "rics": [ASSET]}))
        ws.send(json.dumps({"event": "subscribe", "topic": f"asset:{ASSET}"}))

    def start_ws(self):
        url = "wss://as.stockitymob.com/"
        ws = websocket.WebSocketApp(url,
            header={
                "Host": "as.stockitymob.com",
                "Origin": "https://stockitymob.com",
                "User-Agent": USER_AGENT,
                "authorization-token": AUTH_TOKEN,
                "device-id": DEVICE_ID,
                "device-type": "web"
            },
            on_open=self.on_open, on_message=self.on_message)
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20)

engine = PhoenixRenderBridge()

async def handle_ws(request):
    ws = web.WebSocketResponse(); await ws.prepare(request)
    engine.clients.add(ws)
    try:
        async for msg in ws: pass
    finally:
        engine.clients.remove(ws)
    return ws

app = web.Application()
app.router.add_get('/', lambda r: web.FileResponse('index.html'))
app.router.add_get('/web.html', lambda r: web.FileResponse('web.html'))
app.router.add_get('/ws', handle_ws)

if __name__ == "__main__":
    engine.loop = asyncio.get_event_loop()
    threading.Thread(target=engine.start_ws, daemon=True).start()
    web.run_app(app, port=int(os.environ.get("PORT", 8080)))
