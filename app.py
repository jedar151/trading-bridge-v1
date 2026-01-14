import os
import asyncio
import threading
import json
import ssl
from aiohttp import web
from websocket import WebSocketApp

# --- CONFIG & GLOBALS ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
CLIENTS = set()
PRICE_HISTORY = []

# --- HTML LANGSUNG DI DALAM APP ---
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head><title>ZIROD TEST 4</title></head>
<body style="background:#000;color:#00ff41;font-family:monospace;text-align:center;padding-top:50px;">
    <h2>ZIROD SYSTEM - TEST 4</h2>
    <div id="price" style="font-size:3em;color:#fff;">WAITING...</div>
    <div id="status">Connecting...</div>
    <script>
        const connect = () => {
            const socket = new WebSocket((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws');
            socket.onmessage = (e) => {
                const d = JSON.parse(e.data);
                if(d.price) document.getElementById('price').innerText = d.price.toFixed(8);
                document.getElementById('status').innerText = "LIVE DATA RECEIVED";
            };
            socket.onclose = () => setTimeout(connect, 2000);
        };
        connect();
    </script>
</body>
</html>
"""

# --- LOGIKA ENGINE ---
def run_hunter_engine(loop):
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "data" in data and len(data["data"]) > 0:
                asset = data["data"][0].get("assets", [{}])[0]
                if asset.get("ric") == "Z-CRY/IDX":
                    price = float(asset["rate"])
                    packet = json.dumps({"price": price})
                    # Kirim data ke browser melalui loop utama
                    for client in CLIENTS.copy():
                        loop.call_soon_threadsafe(asyncio.create_task, client.send_str(packet))
        except: pass

    ws = WebSocketApp(
        "wss://as.stockitymob.com/",
        header={"authorization-token": AUTH_TOKEN},
        on_message=on_message
    )
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

# --- WEB SERVER ROUTES ---
async def handle_index(request):
    return web.Response(text=INDEX_HTML, content_type='text/html')

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally:
        CLIENTS.remove(ws)
    return ws

# --- MAIN EXECUTION ---
app = web.Application()
app.add_routes([web.get('/', handle_index), web.get('/ws', handle_ws)])

if __name__ == '__main__':
    # 1. Ambil Loop Utama
    main_loop = asyncio.get_event_loop()
    
    # 2. Jalankan Hunter di Thread Terpisah (Agar tidak menghalangi Port)
    t = threading.Thread(target=run_hunter_engine, args=(main_loop,), daemon=True)
    t.start()
    
    # 3. Jalankan Server Web (Agar Port 8080 terdeteksi Render)
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
