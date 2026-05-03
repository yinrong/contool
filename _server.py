#!/usr/bin/env python3

import asyncio
import json
import logging
import random
import ssl
import string
import os

import aiohttp
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("app")


def _random_padding() -> str:
    length = random.randint(16, 128)
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


class Worker:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self._running = True

    async def start(self):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        self.session = aiohttp.ClientSession(connector=connector)

        backoff = config.RECONNECT_BASE
        while self._running:
            try:
                await self._connect()
                backoff = config.RECONNECT_BASE
            except Exception as e:
                log.warning("Retrying in %ds (%s)", backoff, type(e).__name__)

            if not self._running:
                break
            await asyncio.sleep(backoff + random.uniform(0, 2))
            backoff = min(backoff * 2, config.RECONNECT_MAX)

        await self.session.close()

    def _use_tls(self) -> bool:
        if config.RELAY_TLS == "true":
            return True
        if config.RELAY_TLS == "false":
            return False
        return os.path.exists(config.CERT_FILE) and os.path.exists(config.KEY_FILE)

    async def _connect(self):
        scheme = "wss" if self._use_tls() else "ws"
        url = f"{scheme}://{config.RELAY_ADDR}:{config.RELAY_PORT}{config.WS_PATH}"
        headers = {"Cookie": f"_sid={config.TUNNEL_SECRET}"}

        log.info("Starting")
        async with self.session.ws_connect(url, headers=headers, heartbeat=None) as ws:
            log.info("Ready")

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        asyncio.create_task(self._handle_message(ws, msg.data))
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        log.error("Error: %s", ws.exception())
                        break
            finally:
                heartbeat_task.cancel()

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse):
        try:
            while not ws.closed:
                interval = random.uniform(config.HEARTBEAT_MIN, config.HEARTBEAT_MAX)
                await asyncio.sleep(interval)
                if not ws.closed:
                    await ws.send_str(json.dumps({
                        "type": "ping",
                        "padding": _random_padding(),
                    }))
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, ws: aiohttp.ClientWebSocketResponse, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        if msg.get("type") != "request":
            return

        req_id = msg["id"]
        method = msg.get("method", "POST")
        path = msg.get("path", "/v1/chat/completions")
        headers = msg.get("headers", {})
        body = msg.get("body", {})
        is_stream = body.get("stream", False)

        internal_url = config.INTERNAL_LLM_BASE.rstrip("/") + path

        try:
            if is_stream:
                await self._forward_stream(ws, req_id, method, internal_url, headers, body)
            else:
                await self._forward_normal(ws, req_id, method, internal_url, headers, body)
        except Exception as e:
            log.error("Failed: %s", e)
            await ws.send_str(json.dumps({
                "type": "response",
                "id": req_id,
                "status": 502,
                "body": {"error": {"message": str(e), "type": "proxy_error"}},
            }))

    async def _forward_normal(
        self, ws: aiohttp.ClientWebSocketResponse,
        req_id: str, method: str, url: str, fwd_headers: dict, body: dict,
    ):
        async with self.session.request(
            method, url, json=body, headers=fwd_headers,
            timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT),
        ) as resp:
            resp_body = await resp.json()
            await ws.send_str(json.dumps({
                "type": "response",
                "id": req_id,
                "status": resp.status,
                "headers": {"content-type": resp.headers.get("content-type", "application/json")},
                "body": resp_body,
            }))

    async def _forward_stream(
        self, ws: aiohttp.ClientWebSocketResponse,
        req_id: str, method: str, url: str, fwd_headers: dict, body: dict,
    ):
        async with self.session.request(
            method, url, json=body, headers=fwd_headers,
            timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT),
        ) as resp:
            async for line in resp.content:
                decoded = line.decode() if isinstance(line, bytes) else line
                if decoded.strip():
                    await ws.send_str(json.dumps({
                        "type": "stream_chunk",
                        "id": req_id,
                        "data": decoded,
                    }))

            await ws.send_str(json.dumps({
                "type": "stream_end",
                "id": req_id,
            }))


async def main():
    worker = Worker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
