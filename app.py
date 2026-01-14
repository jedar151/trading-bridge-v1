import os
import json
import ssl
import threading
import asyncio
from aiohttp import web
from websocket import WebSocketApp

# --- CONFIGURATION ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Infinix X6531B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"

# --- GLOBALS ---
CLIENTS = set()
PRICE_HISTORY = []

# --- HTML INTERFACE ---
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ZIROD V1 - TEST 4</title>
    <style>
        body { background: #000; color: #00ff41; font-family: monospace; text-align: center; padding-top: 50px; }
        .monitor { border: 2px solid #00ff41; display: inline-block; padding: 30px; border-radius: 10px; box-shadow: 0 0 20px #00ff41; }
        #price { font-size: 3.5em; color: #fff; margin: 10px 0; font-weight: bold; }
        #rsi { font-size: 1.2em; opacity: 0.8; }
        .status { color: #555; font-size: 0.8em; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="monitor">
        <h2>ZIROD CLOUD SYSTEM</h2>
        <div id="price">--.--------</div>
        <div id="rsi">RSI: --</div>
        <p class="status" id="stat">Initializing Port 8080...</p>
    </div>
    <script>
        function connect() {
            const socket = new WebSocket((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws');
            socket.onopen = () => { document.getElementById('stat').innerText = "CONNECTED TO ENGINE"; };
            socket.onmessage = (e) => {
                const d = JSON.parse(e.data);
                if(d.price) document.getElementById('price').innerText = d.price.toFixed(8);
                if(d.rsi) document.getElementById('rsi').innerText = "RSI: " + d.rsi.toFixed(2);
                document.getElementById('stat').innerText = "LIVE: " + new Date().toLocaleTimeString();
            };
            socket.onclose = () => {
                document.getElementById('stat').innerText = "RECONNECTING...";
                setTimeout(connect, 2000);
            };
        }
        connect();
    </script>
</body>
</html>
"""

# --- ENGINE LOGIC ---
class ZiroEngine:
    def __init__(self, loop):
        self.loop = loop

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1: return 50.0
        deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
        gains = [d for d in deltas if d > 0]
        losses = [abs(d) for d in deltas if d < 0]
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and data["data"]:
                asset = data["data"][0].get("assets", [{}])[0]
                if asset.get("ric") == "Z-CRY/IDX":
                    price = float(asset["rate"])
                    PRICE_HISTORY.append(price)
                    if len(PRICE_HISTORY) > 50: PRICE_HISTORY.pop(0)
                    
                    rsi_val = self.calculate_rsi(PRICE_HISTORY)
                    packet = json.dumps({"price": price, "rsi": rsi_val})
                    
                    # Broadcast ke semua user yang buka web
                    for client in CLIENTS.copy():
                        self.loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(client.send_str(packet))
                        )
        except Exception: pass

    def run(self):
        ws = WebSocketApp(
            "wss://as.stockitymob.com/",
            header={"User-Agent": USER_AGENT, "authorization-token": AUTH_TOKEN},
            on_message=self.on_message
        )
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20)

# --- WEB SERVER HANDLERS ---
async def index_handler(request):
    return web.Response(text=INDEX_HTML, content_type='text/html')

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        CLIENTS.add(ws) # Safety remove dikontrol aiohttp
        if ws in CLIENTS: CLIENTS.remove(ws)
    return ws

# --- APP STARTUP ---
app = web.Application()
app.add_routes([
    web.get('/', index_handler),
    web.get('/ws', ws_handler)
])

if __name__ == '__main__':
    # 1. BUAT LOOP MANUALLY (Obat Python 3.13)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 2. JALANKAN ENGINE DI BACKGROUND THREAD
    def start_engine():
        engine = ZiroEngine(loop)
        engine.run()

    t = threading.Thread(target=start_engine, daemon=True)
    t.start()
    print("🎯 ZIROD ENGINE ONLINE")

    # 3. JALANKAN SERVER (Jawab tantangan Port Render)
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 SERVER STARTING ON PORT {port}")
    
    # Menjalankan app dengan loop yang sudah kita buat
    web.run_app(app, host="0.0.0.0", port=port, loop=loop)
