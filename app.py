import os
import json
import asyncio
import statistics
import aiohttp
from datetime import datetime
from aiohttp import web

# --- KONFIGURASI ---
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
        self.majority_call_pct = 50.0
        self.majority_put_pct = 50.0

    def calculate_rsi(self, period=14):
        if len(self.price_history) < period + 1: return 50.0
        prices = self.price_history[-period:]
        gains = []
        losses = []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            gains.append(max(0, diff))
            losses.append(max(0, -diff))
        
        avg_gain = statistics.mean(gains) if gains else 0
        avg_loss = statistics.mean(losses) if losses else 0
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    async def stockity_provider(self):
        """Menggunakan aiohttp agar satu jalur dengan server Render"""
        url = "wss://as.stockitymob.com/websocket"
        headers = {
            "User-Agent": USER_AGENT,
            "authorization-token": AUTH_TOKEN,
            "device-id": DEVICE_ID,
            "Origin": "https://stockitymob.com"
        }
        
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    print(f"⚡ [CORE] MENGHUBUNGKAN KE STOCKITY...")
                    async with session.ws_connect(url, headers=headers, ssl=False) as ws:
                        # Subscribe
                        await ws.send_str(json.dumps({"action": "subscribe", "rics": [ASSET]}))
                        await ws.send_str(json.dumps({"event": "subscribe", "topic": f"asset:{ASSET}"}))
                        print(f"✅ [CORE] SUBSCRIBED TO {ASSET}")

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                
                                # 1. Opini Mayoritas
                                if data.get("event") == "majority_opinion":
                                    p = data.get("payload", {})
                                    total = p.get("call", 0) + p.get("put", 0)
                                    if total > 0:
                                        self.majority_call_pct = (p["call"] / total) * 100
                                        self.majority_put_pct = (p["put"] / total) * 100

                                # 2. Update Harga
                                elif "data" in data and len(data["data"]) > 0:
                                    item = data["data"][0]
                                    if "assets" in item:
                                        asset_data = item["assets"][0]
                                        if asset_data.get("ric") == ASSET:
                                            self.last_price = float(asset_data["rate"])
                                            self.price_history.append(self.last_price)
                                            if len(self.price_history) > self.max_history: 
                                                self.price_history.pop(0)
                                            
                                            self.current_rsi = self.calculate_rsi()
                                            
                                            # Broadcast Packet ke Browser HP
                                            packet = {
                                                "type": "tick",
                                                "price": self.last_price,
                                                "rsi": round(self.current_rsi, 2),
                                                "call_pct": round(self.majority_call_pct, 1),
                                                "put_pct": round(self.majority_put_pct, 1)
                                            }
                                            await self.broadcast(packet)
                except Exception as e:
                    print(f"❌ [CORE] ERROR: {e}")
                    await asyncio.sleep(5)

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            disconnected = set()
            for client in self.clients:
                try:
                    await client.send_str(msg)
                except:
                    disconnected.add(client)
            self.clients -= disconnected

engine = PhoenixRenderBridge()

async def handle_ws(request):
    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(request)
    engine.clients.add(ws)
    print(f"📶 [BRIDGE] HP CONNECTED (Total: {len(engine.clients)})")
    
    # Kirim sinyal sukses pertama
    await ws.send_str(json.dumps({"status": "connected"}))
    
    try:
        async for msg in ws:
            pass # Menjaga koneksi tetap terbuka
    finally:
        engine.clients.remove(ws)
        print("📶 [BRIDGE] HP DISCONNECTED")
    return ws

async def start_background_tasks(app):
    app['stockity'] = asyncio.create_task(engine.stockity_provider())

async def cleanup_background_tasks(app):
    app['stockity'].cancel()
    await app['stockity']

app = web.Application()
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

# Routes
app.router.add_get('/ws', handle_ws)
# Health check untuk Render
app.router.add_get('/', lambda r: web.Response(text="PHOENIX_BRIDGE_ACTIVE", status=200))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, port=port)

