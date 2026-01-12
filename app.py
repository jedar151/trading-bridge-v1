import json, time, ssl, os, asyncio, threading
from aiohttp import web
from websocket import WebSocketApp

# --- KONFIGURASI FIX ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c" 
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"

BRIDGE_CLIENTS = set()

class StockityBridge:
    def __init__(self, loop):
        self.loop = loop

    async def broadcast(self, data):
        if not BRIDGE_CLIENTS: return
        payload = json.dumps(data)
        for ws in list(BRIDGE_CLIENTS):
            try: await ws.send_str(payload)
            except: BRIDGE_CLIENTS.remove(ws)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and len(data["data"]) > 0:
                asset = data["data"][0].get("assets", [{}])[0]
                if asset.get("ric") == "Z-CRY/IDX":
                    packet = {
                        "price": float(asset["rate"]),
                        "ts": time.time()
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
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    BRIDGE_CLIENTS.add(ws)
    try:
        async for msg in ws: pass
    finally: BRIDGE_CLIENTS.remove(ws)
    return ws

async def main():
    loop = asyncio.get_running_loop()
    bridge = StockityBridge(loop)
    bridge.start()
    app = web.Application()
    app.router.add_get('/', lambda r: web.FileResponse('./index.html'))
    app.router.add_get('/ws', handle_ws)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
