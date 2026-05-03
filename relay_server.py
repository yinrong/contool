#!/usr/bin/env python3
"""
Relay server (runs on B - the machine with public IP).

Serves a camouflage static website on /.
Accepts WebSocket tunnel from C on /ws/notifications.
Proxies API requests from A through the tunnel to C.
"""

import asyncio
import json
import logging
import os
import ssl
import uuid

import aiohttp
from aiohttp import web

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("relay")


class RelayServer:
    def __init__(self):
        self.tunnel_ws: web.WebSocketResponse | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.stream_queues: dict[str, asyncio.Queue] = {}
        self._tunnel_lock = asyncio.Lock()

    async def handle_index(self, request: web.Request) -> web.Response:
        static_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.exists(static_path):
            return web.FileResponse(static_path)
        return web.Response(text="Welcome", content_type="text/html")

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        cookie = request.headers.get("Cookie", "")
        token = next((p.split("=", 1)[1] for p in cookie.split(";") if p.strip().startswith("_sid=")), "")
        if token != config.TUNNEL_SECRET:
            log.warning("Tunnel auth failed from %s", request.remote)
            raise web.HTTPNotFound()

        ws = web.WebSocketResponse(heartbeat=None)
        await ws.prepare(request)
        log.info("Tunnel connected from %s", request.remote)

        async with self._tunnel_lock:
            if self.tunnel_ws is not None and not self.tunnel_ws.closed:
                await self.tunnel_ws.close()
            self.tunnel_ws = ws

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_tunnel_msg(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    log.error("Tunnel error: %s", ws.exception())
        finally:
            log.info("Tunnel disconnected")
            async with self._tunnel_lock:
                if self.tunnel_ws is ws:
                    self.tunnel_ws = None
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("tunnel disconnected"))
            self.pending.clear()
            for q in self.stream_queues.values():
                await q.put(None)
            self.stream_queues.clear()

        return ws

    async def _handle_tunnel_msg(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")
        req_id = msg.get("id")

        if msg_type == "pong":
            return

        if msg_type == "response" and req_id in self.pending:
            fut = self.pending.pop(req_id)
            if not fut.done():
                fut.set_result(msg)

        elif msg_type == "stream_chunk" and req_id in self.stream_queues:
            await self.stream_queues[req_id].put(msg.get("data", ""))

        elif msg_type == "stream_end" and req_id in self.stream_queues:
            await self.stream_queues[req_id].put(None)

    async def handle_api(self, request: web.Request) -> web.StreamResponse:
        auth = request.headers.get("Authorization", "")
        api_key = request.headers.get("x-api-key", "")
        if auth != f"Bearer {config.AUTH_TOKEN}" and api_key != config.AUTH_TOKEN:
            raise web.HTTPNotFound()

        if self.tunnel_ws is None or self.tunnel_ws.closed:
            return web.json_response(
                {"error": {"message": "service unavailable", "type": "server_error"}},
                status=502,
            )

        try:
            body = await request.json()
        except Exception:
            body = {}

        is_stream = body.get("stream", False)
        req_id = uuid.uuid4().hex

        tunnel_msg = json.dumps({
            "type": "request",
            "id": req_id,
            "method": request.method,
            "path": request.path,
            "headers": {k: v for k, v in request.headers.items()
                        if k.lower() in ("authorization", "x-api-key", "content-type",
                                         "anthropic-version", "anthropic-beta")},
            "body": body,
        })

        if is_stream:
            return await self._handle_stream(request, req_id, tunnel_msg)
        else:
            return await self._handle_normal(req_id, tunnel_msg)

    async def _handle_normal(self, req_id: str, tunnel_msg: str) -> web.Response:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self.pending[req_id] = fut

        try:
            await self.tunnel_ws.send_str(tunnel_msg)
            result = await asyncio.wait_for(fut, timeout=config.REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self.pending.pop(req_id, None)
            return web.json_response(
                {"error": {"message": "request timeout", "type": "server_error"}},
                status=504,
            )
        except Exception as e:
            self.pending.pop(req_id, None)
            return web.json_response(
                {"error": {"message": str(e), "type": "server_error"}},
                status=502,
            )

        status = result.get("status", 200)
        resp_body = result.get("body")
        resp_headers = result.get("headers", {})

        content_type = resp_headers.get("content-type", "application/json")
        if isinstance(resp_body, (dict, list)):
            return web.json_response(resp_body, status=status)
        return web.Response(text=str(resp_body), status=status, content_type=content_type)

    async def _handle_stream(
        self, request: web.Request, req_id: str, tunnel_msg: str
    ) -> web.StreamResponse:
        queue: asyncio.Queue = asyncio.Queue()
        self.stream_queues[req_id] = queue

        try:
            await self.tunnel_ws.send_str(tunnel_msg)
        except Exception as e:
            self.stream_queues.pop(req_id, None)
            return web.json_response(
                {"error": {"message": str(e), "type": "server_error"}},
                status=502,
            )

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=config.REQUEST_TIMEOUT)
                except asyncio.TimeoutError:
                    break
                if chunk is None:
                    break
                await response.write(chunk.encode() if isinstance(chunk, str) else chunk)
        finally:
            self.stream_queues.pop(req_id, None)

        return response

    async def handle_catch_all(self, request: web.Request) -> web.Response:
        return await self.handle_index(request)


def create_app() -> web.Application:
    relay = RelayServer()
    app = web.Application()

    app.router.add_get("/", relay.handle_index)
    app.router.add_get(config.WS_PATH, relay.handle_websocket)

    app.router.add_route("*", "/v1/{path:.*}", relay.handle_api)
    app.router.add_route("*", "/api/{path:.*}", relay.handle_api)
    app.router.add_route("*", "/anthropic/{path:.*}", relay.handle_api)

    app.router.add_route("*", "/{path:.*}", relay.handle_catch_all)

    return app


def main():
    app = create_app()

    ssl_ctx = None
    if os.path.exists(config.CERT_FILE) and os.path.exists(config.KEY_FILE):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(config.CERT_FILE, config.KEY_FILE)
        log.info("TLS enabled with %s", config.CERT_FILE)
    else:
        log.warning("No TLS certs found, running without TLS (development only)")

    log.info("Relay server starting on %s:%d", config.RELAY_HOST, config.RELAY_PORT)
    web.run_app(app, host=config.RELAY_HOST, port=config.RELAY_PORT, ssl_context=ssl_ctx)


if __name__ == "__main__":
    main()
