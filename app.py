import os, json, time, threading, asyncio
from aiohttp import web
from websocket import WebSocketApp

# --- DATA HASIL BONGKAR PROFESOR ---
AUTH_TOKEN = "cb1af94b-28f0-4d76-b827-37c4df023c2c"
DEVICE_ID = "c47bb81b535832546db3f7f016eb01a0"
ASSET = "Z-CRY/IDX"

class TitaniumEngine:
    def __init__(self):
        self.clients = set()
        self.last_price = 0
        self.sentiment = {"call": 50, "put": 50}

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            for client in self.clients:
                try: await client.send_str(msg)
                except: pass

    def on_message(self, ws, message):
        try:
            # Membersihkan prefix angka (42, 40) jika ada di protokol Socket.io
            if message.startswith('42'):
                data_str = message[2:]
                raw_list = json.loads(data_str)
                event = raw_list[0]
                payload = raw_list[1] if len(raw_list) > 1 else {}
            else:
                raw = json.loads(message)
                event = raw.get("event")
                payload = raw.get("payload", {})

            # Filter Harga
            price = None
            if event == "quotes_range": price = payload.get("value")
            elif event == "social_trading_deal": price = payload.get("entrie_rate")
            
            if price:
                self.last_price = float(price)
                asyncio.run_coroutine_threadsafe(self.broadcast({"type": "tick", "price": self.last_price}), loop)

            # Filter Sentimen
            if event == "majority_opinion":
                self.sentiment = {"call": payload.get("call"), "put": payload.get("put")}
                asyncio.run_coroutine_threadsafe(self.broadcast({"type": "sentiment", "data": self.sentiment}), loop)
        except: pass

    def on_open(self, ws):
        print(">> TITANIUM ENGINE ONLINE")
        # Protokol Phoenix Join
        ws.send(json.dumps({"event":"phx_join","topic":f"range_stream:{ASSET}","payload":{},"ref":"1"}))
        ws.send(json.dumps({"event":"phx_join","topic":f"asset:{ASSET}","payload":{},"ref":"2"}))
        
        def heartbeat():
            while ws.sock and ws.sock.connected:
                time.sleep(20)
                ws.send(json.dumps({"event":"ping","topic":"connection","payload":{},"ref":"40"}))
        threading.Thread(target=heartbeat, daemon=True).start()

    def start_ws(self):
        # Menggunakan server Asia yang Profesor temukan
        ws_url = "wss://as.stockitymob.com/ws/shell/?EIO=3&transport=websocket"
        self.ws = WebSocketApp(ws_url, 
            header={"authorization-token": AUTH_TOKEN, "device-id": DEVICE_ID},
            on_message=self.on_message, on_open=self.on_open)
        self.ws.run_forever()

engine = TitaniumEngine()
loop = asyncio.new_event_loop()

# --- ROUTES ---
async def handle_ws(request):
    ws = web.WebSocketResponse(); await ws.prepare(request)
    engine.clients.add(ws)
    try: async for msg in ws: pass
    finally: engine.clients.remove(ws)
    return ws

app = web.Application()
app.router.add_get('/', lambda r: web.FileResponse('index.html'))
app.router.add_get('/web.html', lambda r: web.FileResponse('web.html'))
app.router.add_get('/ws', handle_ws)

if __name__ == "__main__":
    threading.Thread(target=engine.start_ws, daemon=True).start()
    web.run_app(app, port=int(os.environ.get("PORT", 8080)))
