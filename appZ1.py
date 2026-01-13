import json
import time
import ssl
import os
import asyncio
import threading
import math
from aiohttp import web
from websocket import WebSocketApp

# --- DATA AUTH & CONFIG ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Infinix X6531B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"

# --- VARIABEL GLOBAL ---
BRIDGE_CLIENTS = set()
PRICE_HISTORY = []

def calculate_logic(prices, period=14):
    """Menghitung RSI & Bollinger Bands secara real-time"""
    if len(prices) < period + 1:
        return {"rsi": 50.0, "trend": "COLLECTING_DATA", "bb_status": "NORMAL"}
    
    # Hitung RSI (Menggunakan Math saja)
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-(i+1)]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Cegah pembagian nol
    if avg_loss == 0: avg_loss = 0.00001
    rs = avg_gain / avg_loss
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

    return {"rsi": round(rsi, 2), "trend": trend, "upper": upper, "lower": lower}

class ZiroEngine:
    def __init__(self, loop):
        self.loop = loop

    async def broadcast(self, data):
        """Kirim data ke semua client PWA (Browser)"""
        if BRIDGE_CLIENTS:
            msg = json.dumps(data)
            # Kirim ke semua client
            for client in BRIDGE_CLIENTS:
                try: await client.send(msg)
                except: BRIDGE_CLIENTS.remove(client)

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
                    
                    # Persiapkan Paket Data
                    packet = {
                        "price": price,
                        "rsi": analysis["rsi"],
                        "trend": analysis["trend"],
                        "bb_upper": analysis["upper"],
                        "bb_lower": analysis["lower"]
                    }
                    
                    # Kirim ke Web Interface
                    asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        except Exception as e:
            pass

    def start_connection(self):
        """Menjalankan Koneksi Stockity di Thread Terpisah (Blocking)"""
        def run():
            while True:
                print(">> Connecting to Stockity Bridge...")
                # Pastikan loop reconnect jalan
                # Jika disconnect, loop ini akan kembali ke atas dan connect ulang
                ws = WebSocketApp(
                    "wss://as.stockitymob.com/",
                    header={"authorization-token": AUTH_TOKEN, "device-id": DEVICE_ID},
                    on_message=self.on_message
                )
                ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                time.sleep(5) # Delay sedikit sebelum reconnect
        
        t = threading.Thread(target=run, daemon=True)
        t.start()

# --- SERVER ROUTES (AIOHTTP) ---

async def index_handler(request):
    """
    Handler Root URL (/).
    Karena file HTML besar, sebaiknya diakses secara LOCAL dari HP.
    Atau jika ingin di-upload, ganti nama file di bawah.
    """
    # Jika Anda upload file 'phoenix_god_eye_cloud.html' ke GitHub, gunakan ini:
    # return web.FileResponse('phoenix_god_eye_cloud.html')
    
    # Sementara ini kita return Status JSON agar Render tidak error 404.
    return web.json_response({"status": "ZIROD AI V1 LIVE", "mode": "CLOUD", "note": "Please run 'phoenix_god_eye_cloud.html' locally and connect to WSS link"})

async def web_handler(request):
    # Sama seperti index
    return web.json_response({"status": "USE LOCAL HTML"})

async def websocket_handler(request):
    """
    Handler untuk Koneksi WebSocket (/ws).
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    BRIDGE_CLIENTS.add(ws)
    print("📶 BROWSER CONNECTED.")
    
    try:
        # Loop koneksi WS (PWS)
        async for msg in ws:
            # Stockity tidak mengirim balas ke HTML, jadi loop ini biarkan hidup
            # Data dikirim lewat broadcast (async)
            pass
    finally:
        BRIDGE_CLIENTS.remove(ws)
        print("📶 BROWSER DISCONNECTED.")

async def status_handler(request):
    """Health Check (Head Request) untuk Render"""
    return web.json_response({"status": "OK", "server": "ZIROD AIOHTTP"})

# --- MAIN ENTRY POINT ---

async def main():
    """
    Fungsi Utama yang akan dijalankan oleh `python app.py`.
    Menggabungkan:
    1. ZiroEngine (Thread).
    2. Web Server (Aiohttp).
    """
    print("╔═════════ ZIROD APP (AIOHTTP) ══════════╗")
    print("║ SERVER: PYTHON AIOHTTP              ║")
    print("╚═══════════════════════════════════════════════════════════════════╗")
    
    # 1. Inisialisasi Engine
    loop = asyncio.get_running_loop()
    engine = ZiroEngine(loop)
    
    # 2. Jalankan Koneksi Stockity di Background Thread
    print("⚡ STARTING STOCKITY PROVIDER...")
    engine.start_connection()
    
    # 3. Buat Web Application
    app = web.Application()
    
    # 4. Daftarkan Routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/web.html', web_handler)
    app.router.add_get('/status', status_handler)
    app.router.add_get('/ws', websocket_handler)
    
    # 5. Jalankan Server
    print("🚀 STARTING SERVER ON PORT 8080...")
    
    # Pakai web.TCPSite agar kompatibel dengan `python app.py` di Render
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner)
    await site.start_server(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    # Kode ini dijalankan saat `python app.py` dipanggil
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSTOPPED.")
