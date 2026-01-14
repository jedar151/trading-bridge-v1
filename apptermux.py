import os, json, asyncio, threading
from aiohttp import web

class MasterBridge:
    def __init__(self):
        self.clients = set()
        self.loop = None

    async def broadcast(self, data):
        if self.clients:
            msg = json.dumps(data)
            for client in list(self.clients):
                try: await client.send_str(msg)
                except: self.clients.remove(client)

bridge = MasterBridge()

# Endpoint rahasia untuk menerima data dari Termux
async def receive_data(request):
    try:
        data = await request.json()
        if bridge.loop:
            # Lempar data ke semua browser yang buka web.html
            asyncio.run_coroutine_threadsafe(bridge.broadcast(data), bridge.loop)
        return web.Response(text="OK")
    except:
        return web.Response(text="Error", status=400)

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    bridge.clients.add(ws)
    try:
        async for msg in ws: pass
    finally:
        bridge.clients.remove(ws)
    return ws

app = web.Application()
app.router.add_post('/push-data', receive_data)
app.router.add_get('/', lambda r: web.FileResponse('index.html'))
app.router.add_get('/web.html', lambda r: web.FileResponse('web.html'))
app.router.add_get('/ws', handle_ws)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bridge.loop = loop
    # Render selalu menggunakan port 10000
    web.run_app(app, port=10000, loop=loop)
