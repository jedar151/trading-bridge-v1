import json, time, ssl, os, asyncio, threading
from aiohttp import web
from websocket import WebSocketApp

# --- DATA AUTH DARI ZIRODV1 ANDA ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"

BRIDGE_CLIENTS = set()
PRICE_HISTORY = []  # Memory System (Ini yang bikin sinyal muncul!)

def calculate_logic(prices, period=14):
    """Menghitung RSI & Bollinger Bands secara real-time"""
    if len(prices) < period + 1:
        return {"rsi": 50.0, "trend": "COLLECTING_DATA", "bb_status": "NORMAL"}
    
    # Hitung RSI
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-(i+1)]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = avg_gain / (avg_loss if avg_loss > 0 else 0.00001)
    rsi = 100 - (100 / (1 + rs))

    # Hitung Bollinger Bands (Sinyal Tambahan)
    sma = sum(prices[-period:]) / period
    variance = sum((x - sma)**2 for x in prices[-period:]) / period
    std_dev = variance**0.5
    upper = sma + (2 * std_dev)
    lower = sma - (2 * std_dev)

    # Logika Penentuan Trend
    current_price = prices[-1]
    if rsi > 70 or current_price > upper: trend = "OVERBOUGHT (SELL)"
    elif rsi < 30 or current_price < lower: trend = "OVERSOLD (BUY)"
    else: trend = "NEUTRAL"

    return {"rsi": round(rsi, 2), "trend": trend}

class ZiroEngine:
    def __init__(self, loop):
        self.loop = loop

    async def broadcast(self, data):
        """Kirim data ke index.html dan web.html"""
        if BRIDGE_CLIENTS:
            msg = json.dumps(data)
            await asyncio.gather(*[ws.send_str(msg) for ws in BRIDGE_CLIENTS], return_exceptions=True)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            # Filter data khusus harga dari asset Crypto IDX
            if "data" in data and data["data"]:
                asset_data = data["data"][0].get("assets", [{}])[0]
                if asset_data.get("ric") == "Z-CRY/IDX":
                    price = float(asset_data["rate"])
                    PRICE_HISTORY.append(price)
                    
                    # Simpan 100 data terakhir agar memori tidak penuh
                    if len(PRICE_HISTORY) > 100: PRICE_HISTORY.pop(0)

                    # Hitung Indikator
                    analysis = calculate_logic(PRICE_HISTORY)
                    
                    packet = {
                        "price": price,
                        "rsi": analysis["rsi"],
                        "trend": analysis["trend"]
                    }
                    # Kirim ke Web Interface
                    asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        except Exception as e:
            print(f"Error parse: {e}")

    def start_connection(self):
        def run():
            while True:
                print(">> Connecting to Stockity Bridge...")
                ws = WebSocketApp(
                    "wss://as.stockitymob.com/",
                    header={"authorization-token": AUTH_TOKEN, "device-id": DEVICE_ID},
                    on_message=self.on_message
                )
                ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                time.sleep(5) # Reconnect jika putus
        threading.Thread(target=run, daemon=True).start()

# --- SERVER ROUTES ---
async def handle_ws(request):
    ws = web.WebSocketResponse(); await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        BRIDGE_CLIENTS.remove(ws)
    return ws

async def main():
    loop = asyncio.get_running_loop()
    engine = ZiroEngine(loop)
    engine.start_connection()

    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse('./index.html'))
    app.router.add_get('/web.html', lambda r: web.FileResponse('./web.html'))
    app.router.add_get('/ws', handle_ws)
    
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    print(f"Server Phoenix Aktif di Port {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
