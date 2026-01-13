import socket
import json
import time
import ssl
import os
import statistics
import threading
import math
import sys
import datetime
from aiohttp import web
from websocket import WebSocketApp

# --- CONFIG ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Infinix X6531B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"

# --- GLOBALS ---
CLIENTS = set()
PRICE_HISTORY = []
LAST_DATA = {"price": 0.0, "rsi": 50.0, "trend": "NEUTRAL"}

# --- INDEX HTML (SIMPLE) ---
# Agar Render punya halaman Index
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head><title>ZIROD CLOUD</title></head>
<body>
<h1 style="color: #00ff41; font-family: monospace; text-align: center; margin-top: 50px;">
    ZIROD SYSTEM ONLINE<br>
    <a href="/ws" style="color: #00ff41; text-decoration: underline;">Connect WS</a>
</h1>
</body>
</html>
"""

# --- ENGINE ---
class ZiroEngine:
    def __init__(self):
        if not os.path.exists("brain"): os.makedirs("brain")
        self.token = AUTH_TOKEN
        self.load_token()

    def load_token(self):
        if os.path.exists("brain/token_cloud.json"):
            try:
                with open("brain/token_cloud.json", "r") as f:
                    d = json.load(f)
                self.token = d.get("token", AUTH_TOKEN)
            except:
                pass

    def calculate_rsi(self):
        if len(PRICE_HISTORY) < 15: return 50.0
        prices = PRICE_HISTORY[-15:]
        gains = [max(p - c, 0) for p, c in zip(prices[1:], prices[:-1])]
        losses = [max(c - p, 0) for p, c in zip(prices[1:], prices[:-1])]
        avg_g = sum(gains) / 15
        avg_l = sum(losses) / 15 if sum(losses) > 0 else 0.0001
        return 100 - (100 / (1 + (avg_g / avg_l)))

    # --- STOCKITY HANDLERS ---
    def on_message(self, ws, message):
        global LAST_DATA, CLIENTS
        try:
            data = json.loads(message)
            if "data" in data and len(data["data"]) > 0:
                asset = data["data"][0].get("assets", [{}])[0]
                if asset.get("ric") == "Z-CRY/IDX":
                    price = float(asset["rate"])
                    PRICE_HISTORY.append(price)
                    if len(PRICE_HISTORY) > 50: PRICE_HISTORY.pop(0)
                    
                    rsi = self.calculate_rsi()
                    
                    # Broadcast ke Browser (Async)
                    try:
                        # Cari event loop di thread utama
                        loop = asyncio.get_event_loop()
                        packet = json.dumps({"price": price, "rsi": rsi})
                        for client in CLIENTS.copy():
                            # Kirim data ke browser
                            asyncio.run_coroutine_threadsafe(
                                client.send(packet), loop
                            )
                    except:
                        pass
        except: pass

    def on_error(self, ws, error):
        pass

    def on_close(self, ws, close_status_code, close_msg):
        pass

    def run_stockity(self):
        """Blocking function. Harus dijalankan di THREAD DAEMON."""
        url = "wss://as.stockitymob.com/"
        ws = WebSocketApp(
            url,
            header={
                "Host": "as.stockitymob.com",
                "Origin": "https://stockitymob.com",
                "User-Agent": USER_AGENT,
                "authorization-token": self.token,
                "device-id": DEVICE_ID,
                "Cookie": f"device_type=web; device_id={DEVICE_ID}; authtoken={self.token}"
            },
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        # Run Forever
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20, ping_timeout=10)

# --- SERVER ROUTES (HTTP) ---
async def index(request):
    """Handle root URL / (Index.html)"""
    return web.Response(text=INDEX_HTML, content_type='text/html')

async def ws_handler(request):
    """Handle WebSocket URL /ws"""
    global CLIENTS
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    CLIENTS.add(ws)
    print("📶 BROWSER CONNECTED.")
    
    try:
        async for msg in ws:
            pass # Browser tidak kirim apa2, data dikirim dari Stockity
    finally:
        CLIENTS.remove(ws)
        print("📶 BROWSER DISCONNECTED.")

# --- STARTUP ENGINE ---
async def start_background_engine():
    """Menjalankan Bot Stockity di Thread Background."""
    engine = ZiroEngine()
    
    def run_engine():
        print("⚡ STARTING ZIROD ENGINE (DAEMON THREAD)...")
        try:
            engine.run_stockity()
        except Exception as e:
            print(f"[X] ENGINE ERROR: {e}")
    
    # Jalankan di Thread Daemon
    # Daemon=True artinya jika thread mati, server TIDAK ikut mati.
    t = threading.Thread(target=run_engine, daemon=True)
    t.start()

# --- MAIN ASGI (AIOHTTP) ---
app = web.Application()

# Tambahkan Routes
app.add_routes([
    web.get('/', index),      # Halaman Index
    web.get('/ws', ws_handler),  # Endpoint WebSocket
])

# --- STARTUP EVENT ---
app.on_startup.append(lambda app: start_background_engine())

# --- RUNNER (CLI) ---
if __name__ == '__main__':
    web.run_app(app, host="0.0.0.0", port=8080)
