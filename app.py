import json, time, ssl, os, asyncio, threading, requests
from aiohttp import web
from websocket import WebSocketApp

# --- CONFIGURATION ---
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "cb1af94b-28f0-4d76-b829-37c4df023c2c")
DEVICE_ID = os.environ.get("DEVICE_ID", "c47bb81b535832546db3f7f016eb01a0")

BRIDGE_CLIENTS = set()
PRICE_HISTORY = []

def calculate_indicators(prices):
    if len(prices) < 15:
        return {"rsi": 50.0, "ema": prices[-1] if prices else 0}
    
    # Simple RSI
    gains = []
    losses = []
    for i in range(1, 15):
        diff = prices[-i] - prices[-(i+1)]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    rs = avg_gain / (avg_loss if avg_loss > 0 else 0.00001)
    rsi = 100 - (100 / (1 + rs))
    
    # EMA 20
    ema = sum(prices[-20:]) / len(prices[-20:])
    
    return {"rsi": round(rsi, 2), "ema": round(ema, 6)}

class TitaniumEngine:
    def __init__(self, loop):
        self.loop = loop
        self.ws = None

    async def broadcast(self, data):
        if BRIDGE_CLIENTS:
            msg = json.dumps(data)
            await asyncio.gather(*[client.send_str(msg) for client in list(BRIDGE_CLIENTS)], return_exceptions=True)

    def on_message(self, ws, message):
        try:
            raw = json.loads(message)
            # Support for both single and batch updates
            data_list = raw.get("data", [raw]) if isinstance(raw, dict) else []
            
            for item in data_list:
                assets = item.get("assets", [])
                for asset in assets:
                    if asset.get("ric") == "Z-CRY/IDX":
                        price = float(asset.get("rate") or asset.get("price"))
                        self.process_tick(price)
        except:
            pass

    def process_tick(self, price):
        PRICE_HISTORY.append(price)
        if len(PRICE_HISTORY) > 100: PRICE_HISTORY.pop(0)
        
        ind = calculate_indicators(PRICE_HISTORY)
        
        # Data Packet for Frontend
        packet = {
            "price": price,
            "rsi": ind["rsi"],
            "ema": ind["ema"],
            "bb_up": ind["ema"] * 1.0008,
            "bb_low": ind["ema"] * 0.9992,
            "timestamp": time.strftime('%H:%M:%S')
        }
        
        asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        # Terminal log for Render monitoring
        if len(PRICE_HISTORY) % 5 == 0: 
            print(f">> TITAN TICK: {price} | RSI: {ind['rsi']}")

    def on_open(self, ws):
        print(">> TITAN CORE ONLINE: SUBSCRIBING TO STREAM...")
        # Dual-Command Strategy for high compatibility
        ws.send(json.dumps({"type": "subscribe", "assets": [{"ric": "Z-CRY/IDX"}]}))
        ws.send(json.dumps({"type": "subscribe_quotes", "rics": ["Z-CRY/IDX"]}))

    def start(self):
        def run():
            while True:
                try:
                    self.ws = WebSocketApp(
                        "wss://as.stockitymob.com/",
                        header={
                            "authorization-token": AUTH_TOKEN, 
                            "device-id": DEVICE_ID,
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
                        },
                        on_message=self.on_message,
                        on_open=self.on_open
                    )
                    # Increased ping for Cloud Stability
                    self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20, ping_timeout=10)
                except: pass
                time.sleep(5)
        threading.Thread(target=run, daemon=True).start()

async def handle_ws(request):
    ws = web.WebSocketResponse(autoping=True, heartbeat=30.0)
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        BRIDGE_CLIENTS.discard(ws)
    return ws

async def main():
    loop = asyncio.get_running_loop()
    TitaniumEngine(loop).start()
    
    app = web.Application()
    
    # Deteksi lokasi folder saat ini
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Jalur file absolut
    index_path = os.path.join(base_dir, 'index.html')
    web_path = os.path.join(base_dir, 'web.html')

    # Cek keberadaan file di Log Render untuk diagnosa
    if not os.path.exists(index_path):
        print(f"!! PERINGATAN: File index.html tidak ditemukan di {index_path}")
    if not os.path.exists(web_path):
        print(f"!! PERINGATAN: File web.html tidak ditemukan di {web_path}")

    # Handler File yang lebih stabil
    async def serve_index(request):
        return web.FileResponse(index_path)

    async def serve_web(request):
        return web.FileResponse(web_path)

    # Routing
    app.router.add_get('/', serve_index)
    app.router.add_get('/web.html', serve_web)
    app.router.add_get('/ws', handle_ws)
    
    # Jalankan Server
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"--- TITANIUM SERVER READY ON PORT {port} ---")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
