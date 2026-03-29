import asyncio
import json
import logging
import os
import threading
from queue import Queue
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websockets

logger = logging.getLogger(__name__)

UI_HOST = "127.0.0.1"
UI_HTTP_PORT = 8766
UI_WS_PORT = 8765
UI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui"))

_loop: asyncio.AbstractEventLoop | None = None
_clients: set = set()
_http_thread: threading.Thread | None = None
_http_server: ThreadingHTTPServer | None = None
_ws_server = None
_last_state = {"estado": "idle", "mensagem": "Sistema em espera."}
_listeners: list = []


async def _ws_handler(websocket):
    _clients.add(websocket)
    try:
        await websocket.send(json.dumps(_last_state, ensure_ascii=False))
        async for _ in websocket:
            pass
    finally:
        _clients.discard(websocket)


def _start_http_server():
    global _http_server
    handler = partial(SimpleHTTPRequestHandler, directory=UI_DIR)
    _http_server = ThreadingHTTPServer((UI_HOST, UI_HTTP_PORT), handler)
    _http_server.serve_forever()


async def start(loop: asyncio.AbstractEventLoop):
    global _loop, _http_thread, _ws_server
    if _loop is not None:
        return

    _loop = loop

    if _http_thread is None:
        _http_thread = threading.Thread(target=_start_http_server, daemon=True, name="orion-ui-http")
        _http_thread.start()

    _ws_server = await websockets.serve(_ws_handler, UI_HOST, UI_WS_PORT)
    logger.info("🛰️ Interface Orion disponível em http://%s:%s", UI_HOST, UI_HTTP_PORT)


async def _broadcast_state(payload: dict):
    global _last_state
    _last_state = payload
    for listener in list(_listeners):
        try:
            listener(payload)
        except Exception:
            logger.exception("Falha ao notificar listener local da interface.")
    if not _clients:
        return

    message = json.dumps(payload, ensure_ascii=False)
    stale = []
    for client in list(_clients):
        try:
            await client.send(message)
        except Exception:
            stale.append(client)
    for client in stale:
        _clients.discard(client)


async def emit_state(estado: str, mensagem: str = ""):
    await _broadcast_state({"estado": estado, "mensagem": mensagem})


def emit_state_sync(estado: str, mensagem: str = ""):
    if _loop is None:
        payload = {"estado": estado, "mensagem": mensagem}
        for listener in list(_listeners):
            try:
                listener(payload)
            except Exception:
                logger.exception("Falha ao notificar listener local da interface.")
        return
    asyncio.run_coroutine_threadsafe(
        _broadcast_state({"estado": estado, "mensagem": mensagem}),
        _loop,
    )


def register_listener(callback):
    if callback not in _listeners:
        _listeners.append(callback)
        try:
            callback(_last_state)
        except Exception:
            logger.exception("Falha ao enviar estado inicial ao listener.")


def unregister_listener(callback):
    if callback in _listeners:
        _listeners.remove(callback)


async def stop():
    global _http_server, _ws_server, _loop
    if _ws_server is not None:
        _ws_server.close()
        await _ws_server.wait_closed()
        _ws_server = None

    if _http_server is not None:
        _http_server.shutdown()
        _http_server.server_close()
        _http_server = None

    _loop = None
