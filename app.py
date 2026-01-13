import os
import json
import asyncio
import threading
import ssl
import websocket
import time
from aiohttp import web

# --- IDENTITAS KENDALI ---
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
ASSET = "Z-CRY/IDX"

class SingaporeTester:
    def __init__(self):
        self.clients = set()
        self.loop = None
        self.last_price = 0.0

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            for client in list(self.clients):
                try: 
                    await client.send_str(msg)
                except: 
                    self.clients.remove(client)

    def on_message(self, ws, message):
        # Abaikan heartbeat protokol Engine.io
        if message in ['2', '3']: return
        
        try:
            # Handle pesan jabat tangan awal '40'
            if message == '40':
                print(">> HANDSHAKE 40 DITERIMA - MENGIRIM SUBSCRIPTION")
                ws.send(json.dumps({"action": "subscribe", "rics": [ASSET]}))
                ws.send(json.dumps({"event": "subscribe", "topic": f"asset:{ASSET}"}))
                return

            # Bersihkan prefix protokol 42 jika ada
            clean_msg = message
            if message.startswith('42'):
                clean_msg = message[2:]
            
            data = json.loads(clean_msg)

            # Ekstraksi Data Harga (Format Array atau Object)
            target = data[1] if isinstance(data, list) and len(data) > 1 else data
            
            if "data" in target:
                for item in target["data"]:
                    if "assets" in item:
                        asset_info = item["assets"][0]
                        if asset_info.get("ric") == ASSET:
                            self.last_price = float(asset_info["rate"])
                            
                            # Paket Kiriman untuk web.html
                            packet = {
                                "type": "tick",
                                "price": self.last_price,
                                "rsi": 50.0, # Analisa nyusul sesuai instruksi Prof
                                "countdown": 30
                            }
                            
                            if self.loop:
                                asyncio.run_coroutine_threadsafe(self.broadcast(packet), self.loop)
        except:
            pass

    def on_open(self, ws):
        print(">> KONEKSI TERBUKA - MENGIRIM PROBE")
        # Protokol Engine.io membutuhkan jabat tangan awal
        ws.send("2probe")
        ws.send("5")

    def run_ws(self):
        # Menggunakan endpoint shell yang lebih kuat
        url = "wss://as.stockitymob.com/ws/shell/?EIO=3&transport=websocket"
        while True:
            try:
                ws = websocket.WebSocketApp(url,
                    header={
                        "Host": "as.stockitymob.com",
                        "Origin": "https://stockitymob.com",
                        "User-Agent": USER_AGENT,
                        "authorization-token": AUTH_TOKEN,
                        "Cookie": f"authtoken={AUTH_TOKEN}; device_id={DEVICE_ID}"
                    },
                    on_open=self.on_open, 
                    on_message=self.on_message)
                
                # Gunakan SSL Bypass sesuai taktik Termux Profesor
                ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=25, ping_timeout=10)
            except Exception as e:
                print(f">> KONEKSI DROP: {e}")
            time.sleep(5)

tester = SingaporeTester()

# --- WEB SERVER ROUTING ---
async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    tester.clients.add(ws)
    print(f">> DASHBOARD TERHUBUNG (TOTAL: {len(tester.clients)})")
    try:
        async for msg in ws: pass
    finally:
        tester.clients.add(ws)
    return ws

app = web.Application()
app.router.add_get('/', lambda r: web.FileResponse('index.html'))
app.router.add_get('/web.html', lambda r: web.FileResponse('web.html'))
app.router.add_get('/ws', handle_ws)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tester.loop = loop
    
    # Jalankan Mesin Pengambil Data
    threading.Thread(target=tester.run_ws, daemon=True).start()
    
    # KUNCI UTAMA: Gunakan Port 10000 agar sinkron dengan Render
    print(">> MEMBUKA SIARAN PADA PORT 10000")
    web.run_app(app, port=10000, loop=loop)
