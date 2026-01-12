import json, time, ssl, os, asyncio, threading
from aiohttp import web
from websocket import WebSocketApp

# --- DATA DARI ZIRODV1 ANDA ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c" 
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"

BRIDGE_CLIENTS = set()
PRICE_HISTORY = [] # Memory System

def get_indicators(prices, period=14):
    if len(prices) < period:
        return {"rsi": 50.0, "trend": "SCANNING", "bb_u": 0, "bb_l": 0}
    
    # 1. Hitung RSI
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [c if c > 0 else 0 for c in changes[-period:]]
    losses = [-c if c < 0 else 0 for c in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = avg_gain / (avg_loss if avg_loss > 0 else 0.00001)
    rsi = 100 - (100 / (1 + rs))

    # 2. Hitung Bollinger Bands (BB)
    sma = sum(prices[-period:]) / period
    variance = sum((x - sma)**2 for x in prices[-period:]) / period
    std_dev = variance**0.5
    upper = sma + (2 * std_dev)
    lower = sma - (2 * std_dev)

    # 3. Tentukan Trend
    trend = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
    
    return {"rsi": round(rsi, 2), "trend": trend, "bb_u": upper, "bb_l": lower}

class ZiroBridge:
    def __init__(self, loop):
        self.loop = loop

    async def broadcast(self, message):
        for ws in list(BRIDGE_CLIENTS):
            try: await ws.send_str(json.dumps(message))
            except: BRIDGE_CLIENTS.remove(ws)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and data["data"]:
                asset = data["data"][0].get("assets", [{}])[0]
                if asset.get("ric") == "Z-CRY/IDX":
                    curr_price = float(asset["rate"])
                    PRICE_HISTORY.append(curr_price)
                    if len(PRICE_HISTORY) > 100: PRICE_HISTORY.pop(0)

                    ind = get_indicators(PRICE_HISTORY)
                    packet = {
                        "price": curr_price,
                        "rsi": ind["rsi"],
                        "trend": ind["trend"],
                        "bb_u": ind["bb_u"],
                        "bb_l": ind["bb_l"]
                    }
                    asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        except: pass

    def start(self):
        def run():
            while True:
                try:
                    ws = WebSocketApp("wss://as.stockitymob.com/",
                        header={"authorization-token": AUTH_TOKEN, "device-id": DEVICE_ID},
                        on_message=self.on_message)
                    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                except: time.sleep(5)
        threading.Thread(target=run, daemon=True).start()

async def handle_ws(request):
    ws = web.WebSocketResponse(); await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    try: 
        async for msg in ws: pass
    finally: BRIDGE_CLIENTS.remove(ws)
    return ws

async def main():
    loop = asyncio.get_running_loop()
    bridge = ZiroBridge(loop); bridge.start()
    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse('./index.html'))
    app.router.add_get('/ws', handle_ws)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
