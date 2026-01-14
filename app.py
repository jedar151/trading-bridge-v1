import socket
import json
import time
import ssl
import os
import statistics
import threading
import math
import asyncio
from aiohttp import web
from websocket import WebSocketApp

# --- CONFIG ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Infinix X6531B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"

# --- GLOBALS ---
CLIENTS = set()
PRICE_HISTORY = []

# --- INDEX HTML (Tampilan Test 4) ---
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ZIROD TEST 4</title>
    <style>
        body { background: #000; color: #00ff41; font-family: monospace; text-align: center; padding-top: 50px; }
        .monitor { border: 2px solid #00ff41; display: inline-block; padding: 30px; border-radius: 10px; }
        #price { font-size: 3em; color: #fff; margin: 10px 0; font-weight: bold; }
        .status { color: #555; font-size: 0.8em; }
    </style>
</head>
<body>
    <div class="monitor">
        <h2>ZIROD ENGINE - TEST 4</h2>
        <div id="price">AWAITING...</div>
        <div id="rsi">RSI: --</div>
        <p class="status" id="stat">Connecting to Socket...</p>
    </div>
    <script>
        function connect() {
            const socket = new WebSocket((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws');
            socket.onopen = () => document.getElementById('stat').innerText = "CONNECTED TO SERVER";
            socket.onmessage = (e) => {
                const d = JSON.parse(e.data);
                if(d.price) document.getElementById('price').innerText = d.price.toFixed(8);
                if(d.rsi) document.getElementById('rsi').innerText = "RSI: " + d.rsi.toFixed(2);
                document.getElementById('stat').innerText = "LIVE DATA: " + new Date().toLocaleTimeString();
            };
            socket.onclose = () => setTimeout(connect, 2000);
        }
        connect();
    </script>
</body>
</html>
"""

# --- ENGINE ---
class ZiroEngine:
    def __init__(self, loop):
        self.token = AUTH_TOKEN
        self.loop = loop # Simpan loop utama di sini

    def calculate_rsi(self):
        if len(PRICE_HISTORY) < 15: return 50.0
        prices = PRICE_HISTORY[-15:]
        gains = [max(p - c, 0) for p, c in zip(prices[1:], prices[:-1])]
        losses = [max(c - p, 0) for p, c in zip(prices[1:], prices[:-1])]
        avg_g = sum(gains) / 15
        avg_l = sum(losses) / 15 if sum(losses) > 0 else 0.0001
        return 100 - (100 / (1 + (avg_g / avg_l)))

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and len(data["data"]) > 0:
                asset = data["data"][0].get("assets", [{}])[0]
                if asset.get("ric") == "Z-CRY/IDX":
                    price = float(asset["rate"])
                    PRICE_HISTORY.append(price)
                    if len(PRICE_HISTORY) > 50: PRICE_HISTORY.pop(0)
                    rsi = self.calculate_rsi()
                    
                    # BROADCAST AMAN KE SEMUA CLIENT
                    packet = json.dumps({"price": price, "rsi": rsi})
                    for client in CLIENTS.copy():
                        self.loop.call_soon_threadsafe(asyncio.create_task, client.send_str(packet))
        except: pass

    def run_stockity(self):
        ws = WebSocketApp(
            "wss://as.stockitymob.com/",
            header={"User-Agent": USER_AGENT, "authorization-token": self.token},
            on_message=self.on_message
        )
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20)

# --- ROUTES ---
async def index(request):
    return web.Response(text=INDEX_HTML, content_type='text/html')

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        CLIENTS.remove(ws)
    return ws

# --- STARTUP ---
app = web.Application()
app.add_routes([web.get('/', index), web.get('/ws', ws_handler)])

if __name__ == '__main__':
    # Pastikan kita punya loop yang benar sebelum thread jalan
    loop = asyncio.get_event_loop()
    
    def start_engine():
        engine = ZiroEngine(loop)
        engine.run_stockity()

    threading.Thread(target=start_engine, daemon=True).start()
    
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
