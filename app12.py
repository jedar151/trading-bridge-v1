import json, time, ssl, os, asyncio, threading, requests
from aiohttp import web
from websocket import WebSocketApp

# --- KONFIGURASI ---
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "cb1af94b-28f0-4d76-b82).37c4df023c2c")
DEVICE_ID = os.environ.get("DEVICE_ID", "c47bb81b535832546db3f7f016eb01a0")

BRIDGE_CLIENTS = set()
PRICE_HISTORY = []

def calculate_logic(prices, period=14):
    if len(prices) < period + 1:
        return {"rsi": 50.0, "trend": "COLLECTING"}
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-(i+1)]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = avg_gain / (avg_loss if avg_loss > 0 else 0.00001)
    rsi = 100 - (100 / (1 + rs))
    trend = "UP" if prices[-1] > (sum(prices[-20:])/20 if len(prices)>=20 else prices[0]) else "DOWN"
    return {"rsi": round(rsi, 2), "trend": trend}

class ZiroEngine:
    def __init__(self, loop):
        self.loop = loop
        self.ws = None

    async def broadcast(self, data):
        if BRIDGE_CLIENTS:
            msg = json.dumps(data)
            for client in list(BRIDGE_CLIENTS):
                try: await client.send_str(msg)
                except: BRIDGE_CLIENTS.discard(client)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            # Menangkap data dari berbagai jenis pesan Stockity
            target = data.get("data", []) if "data" in data else [data]
            for item in target:
                assets = item.get("assets", [])
                for asset in assets:
                    if asset.get("ric") == "Z-CRY/IDX":
                        self.process_price(float(asset["rate"]))
        except: pass

    def process_price(self, price):
        PRICE_HISTORY.append(price)
        if len(PRICE_HISTORY) > 100: PRICE_HISTORY.pop(0)
        analysis = calculate_logic(PRICE_HISTORY)
        packet = {
            "price": price, "rsi": analysis["rsi"], 
            "trend": analysis["trend"], "timestamp": time.time(),
            "ema": sum(PRICE_HISTORY[-10:])/10 if len(PRICE_HISTORY)>=10 else price
        }
        asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        print(f">> STREAMING: {price}")

    def on_open(self, ws):
        print(">> JEMBATAN TERBUKA. MENGIRIM SURAT PERINTAH...")
        # Perintah 1: Subscribe Asset
        ws.send(json.dumps({"type": "subscribe", "assets": [{"ric": "Z-CRY/IDX"}]}))
        # Perintah 2: Aktifkan Quote Stream
        ws.send(json.dumps({"type": "subscribe_quotes", "rics": ["Z-CRY/IDX"]}))
        
    def start_connection(self):
        def run_ws():
            while True:
                try:
                    self.ws = WebSocketApp(
                        "wss://as.stockitymob.com/",
                        header={"authorization-token": AUTH_TOKEN, "device-id": DEVICE_ID},
                        on_message=self.on_message,
                        on_open=self.on_open
                    )
                    self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=15)
                except: pass
                time.sleep(5)

        def run_fetch_fallback():
            # Backup: Ambil data via HTTP jika WS macet
            while True:
                try:
                    # Simulasi fetch jika WS tidak memberikan data dalam 10 detik
                    if not BRIDGE_CLIENTS: continue
                    time.sleep(10)
                except: pass

        threading.Thread(target=run_ws, daemon=True).start()
        threading.Thread(target=run_fetch_fallback, daemon=True).start()

async def handle_ws(request):
    ws = web.WebSocketResponse(autoping=True, heartbeat=30.0)
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    return ws

async def main():
    loop = asyncio.get_running_loop()
    ZiroEngine(loop).start_connection()
    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse('./index.html'))
    app.router.add_get('/web.html', lambda r: web.FileResponse('./web.html'))
    app.router.add_get('/ws', handle_ws)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', port).start()
    print(f"TITANIUM SERVER LIVE ON PORT {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
