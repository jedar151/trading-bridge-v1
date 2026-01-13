import json
import time
import ssl
import os
import asyncio
import threading
from aiohttp import web
from websocket import WebSocketApp

# --- KONFIGURASI ---
# Jika di Render, sebaiknya set AUTH_TOKEN dan DEVICE_ID di Environment Variables
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "cb1af94b-28f0-4d76-b827-37c4df023c2c")
DEVICE_ID = os.environ.get("DEVICE_ID", "c47bb81b535832546db3f7f016eb01a0")

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
        self.ws = None 

    async def broadcast(self, data):
        if BRIDGE_CLIENTS:
            msg = json.dumps(data)
            for client in list(BRIDGE_CLIENTS):
                try:
                    await client.send_str(msg)
                except Exception as e:
                    BRIDGE_CLIENTS.discard(client)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            
            # --- DEBUGGING: Cetak data mentah ---
            # Ini akan muncul di Terminal/Layar Logs agar kita tahu data masuk atau tidak
            print(f">> RAW DATA: {str(data)[:200]}") 
            # ------------------------------------

            if "data" in data and data["data"]:
                for item in data["data"]:
                    assets = item.get("assets", [])
                    for asset in assets:
                        # Filter untuk aset spesifik
                        if asset.get("ric") == "Z-CRY/IDX":
                            try:
                                price = float(asset["rate"])
                                PRICE_HISTORY.append(price)
                                if len(PRICE_HISTORY) > 100: PRICE_HISTORY.pop(0)
                                
                                analysis = calculate_logic(PRICE_HISTORY)
                                packet = {
                                    "price": price,
                                    "rsi": analysis["rsi"],
                                    "trend": analysis["trend"],
                                    "timestamp": time.time()
                                }
                                # Kirim data ke browser
                                asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
                                
                                # Cetak di terminal jika berhasil mengambil harga
                                print(f">> UPDATE HARGA: {price} - TREND: {analysis['trend']}")
                            except ValueError:
                                pass 
        except Exception as e:
            print(f">> ERROR PARSING: {e}")

    def on_open(self, ws):
        print(">> TERHUBUNG KE STOCKITY STREAM")

    def on_error(self, ws, error):
        print(f">> WEBSOCKET ERROR: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(">> KONEKSI TERPUTUS, MENGHUBUNGKAN ULANG DALAM 5 DETIK...")

    def start_connection(self):
        def run():
            while True:
                try:
                    print(">> MENGHUBUNGKAN KE SERVER STOCKITY...")
                    
                    # Opsi SSL
                    sslopt = {"cert_reqs": ssl.CERT_NONE}
                    
                    self.ws = WebSocketApp(
                        "wss://as.stockitymob.com/",
                        header={
                            "authorization-token": AUTH_TOKEN, 
                            "device-id": DEVICE_ID
                        },
                        on_message=self.on_message,
                        on_open=self.on_open,
                        on_error=self.on_error,
                        on_close=self.on_close
                        # TANPA ping_interval agar kompatibel semua versi
                    )
                    
                    self.ws.run_forever(sslopt=sslopt)
                except Exception as e:
                    print(f">> ERROR KRITIS: {e}")
                # Retry setiap 5 detik jika putus
                time.sleep(5)
        
        # Jalankan di thread terpisah agar tidak memblokir server
        t = threading.Thread(target=run, daemon=True)
        t.start()

# --- SERVER HANDLERS ---
async def handle_ws(request):
    ws = web.WebSocketResponse(autoping=True, heartbeat=30.0)
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    print(f">> WEB CLIENT TERHUBUNG (Total Klien: {len(BRIDGE_CLIENTS)})")
    
    try:
        async for msg in ws:
            pass
    finally:
        BRIDGE_CLIENTS.discard(ws)
        print(">> WEB CLIENT KELUAR")
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
    
    # Ambil port dari Environment (Render) atau default 8080 (Lokal)
    port = int(os.environ.get("PORT", 8080))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print("-" * 30)
    print(f"ZIROD SYSTEM ONLINE - PORT {port}")
    print("-" * 30)
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    asyncio.run(main())
