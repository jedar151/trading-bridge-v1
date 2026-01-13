import os
import json
import time
import threading
import asyncio
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
        self.loop = None

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            for client in list(self.clients):
                try:
                    await client.send_str(msg)
                except:
                    self.clients.remove(client)

    def on_message(self, ws, message):
        try:
            # Bypass Protokol Socket.io (42)
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
            if event == "quotes_range":
                price = payload.get("value")
            elif event == "social_trading_deal":
                price = payload.get("entrie_rate")
            
            if price and self.loop:
                self.last_price = float(price)
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.broadcast({"type": "tick", "price": self.last_price}))
                )

            # Filter Sentimen
            if event == "majority_opinion" and self.loop:
                self.sentiment = {"call": payload.get("call"), "put": payload.get("put")}
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.broadcast({"type": "sentiment", "data": self.sentiment}))
                )
        except:
            pass

    def on_open(self, ws):
        print(">> TITANIUM ENGINE: CONNECTION ESTABLISHED")
        # Protokol Join Channel Stockity
        ws.send(json.dumps({"event":"phx_join","topic":f"range_stream:{ASSET}","payload":{},"ref":"1"}))
        ws.send(json.dumps({"event":"phx_join","topic":f"asset:{ASSET}","payload":{},"ref":"2"}))
        
        # Heartbeat Keep-Alive
        def heartbeat():
            while ws.sock and ws.sock.connected:
                time.sleep(20)
                try: ws.send(json.dumps({"event":"ping","topic":"connection","payload":{},"ref":"40"}))
                except: break
        threading.Thread(target=heartbeat, daemon=True).start()

    def start_ws(self):
        # URL & HEADERS PENYAMARAN (PENTING!)
        ws_url = "wss://as.stockitymob.com/ws/shell/?EIO=3&transport=websocket"
        headers = {
            "Authorization-Token": AUTH_TOKEN,
            "Device-Id": DEVICE_ID,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://stockitymob.com"
        }
        
        self.ws = WebSocketApp(ws_url, 
            header=headers,
            on_message=self.on_message, 
            on_open=self.on_open,
            on_error=lambda ws, err: print(f"Socket Error: {err}"))
        self.ws.run_forever()

engine = TitaniumEngine()

# --- SERVER ROUTES ---
async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    engine.clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == 'close': await ws.close()
    finally:
        engine.clients.remove(ws)
    return ws

async def index_page(request):
    return web.FileResponse('index.html')

async def dash_page(request):
    return web.FileResponse('web.html')

app = web.Application()
app.router.add_get('/', index_page)
app.router.add_get('/web.html', dash_page)
app.router.add_get('/ws', handle_ws)

if __name__ == "__main__":
    engine.loop = asyncio.get_event_loop()
    threading.Thread(target=engine.start_ws, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, port=port)
