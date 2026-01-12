import json, time, ssl, os, asyncio, threading
from aiohttp import web
from websocket import WebSocketApp

# --- DATA AUTH DARI ZIRODV1 ANDA ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"

BRIDGE_CLIENTS = set()
PRICE_HISTORY = []

def calculate_logic(prices, period=14):
    if len(prices) < period + 1:
        return {"rsi": 50.0, "trend": "COLLECTING_DATA"}
    
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-(i+1)]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = avg_gain / (avg_loss if avg_loss > 0 else 0.00001)
    rsi = 100 - (100 / (1 + rs))

    current_price = prices[-1]
    if rsi > 70: trend = "OVERBOUGHT"
    elif rsi < 30: trend = "OVERSOLD"
    else: trend = "NEUTRAL"

    return {"rsi": round(rsi, 2), "trend": trend}

class ZiroEngine:
    def __init__(self, loop):
        self.loop = loop

    async def broadcast(self, data):
        if BRIDGE_CLIENTS:
            msg = json.dumps(data)
            # Menggunakan list untuk menghindari RuntimeError set change
            for client in list(BRIDGE_CLIENTS):
                try:
                    await client.send_str(msg)
                except:
                    BRIDGE_CLIENTS.remove(client)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and data["data"]:
                # Menangani berbagai struktur data Stockity
                for item in data["data"]:
                    assets = item.get("assets", [])
                    for asset in assets:
                        if asset.get("ric") == "Z-CRY/IDX":
                            price = float(asset["rate"])
                            PRICE_HISTORY.append(price)
                            if len(PRICE_HISTORY) > 100: PRICE_HISTORY.pop(0)
                            
                            analysis = calculate_logic(PRICE_HISTORY)
                            packet = {
                                "price": price,
                                "rsi": analysis["rsi"],
                                "trend": analysis["trend"]
                            }
                            asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        except:
            pass

    def start_connection(self):
        def run():
            while True:
                try:
                    ws = WebSocketApp(
                        "wss://as.stockitymob.com/",
                        header={"authorization-token": AUTH_TOKEN, "device-id": DEVICE_ID},
                        on_message=self.on_message
                    )
                    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                except:
                    pass
                time.sleep(5) 
        threading.Thread(target=run, daemon=True).start()

# --- SERVER HANDLERS ---
async def handle_ws(request):
    ws = web.WebSocketResponse(autoping=True, heartbeat=30.0)
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    print(">> New Web Client Connected")
    try:
        async for msg in ws:
            pass
    finally:
        BRIDGE_CLIENTS.remove(ws)
    return ws

async def handle_index(request):
    return web.FileResponse('./index.html')

async def handle_web(request):
    return web.FileResponse('./web.html')

async def main():
    loop = asyncio.get_running_loop()
    engine = ZiroEngine(loop)
    engine.start_connection()

    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/web.html', handle_web)
    app.router.add_get('/ws', handle_ws)
    
    # Render butuh port dari environment variable
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"PHOENIX CORE LIVE ON PORT {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
