import asyncio
import importlib
import os
import ssl
import sys

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_TUNNEL_SECRET = "tun-test-secret-for-e2e"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_certs():
    cert_path = os.path.join(PROJECT_ROOT, "certs", "server.crt")
    if not os.path.exists(cert_path):
        sys.path.insert(0, PROJECT_ROOT)
        from gen_cert import generate_cert
        generate_cert(cert_dir=os.path.join(PROJECT_ROOT, "certs"))


def _setup_env(mock_llm_port, relay_port):
    os.environ["RELAY_HOST"] = "127.0.0.1"
    os.environ["RELAY_PORT"] = str(relay_port)
    os.environ["RELAY_ADDR"] = "127.0.0.1"
    os.environ["TUNNEL_SECRET"] = TEST_TUNNEL_SECRET
    os.environ["INTERNAL_LLM_BASE"] = f"http://127.0.0.1:{mock_llm_port}"
    os.environ["CERT_FILE"] = os.path.join(PROJECT_ROOT, "certs", "server.crt")
    os.environ["KEY_FILE"] = os.path.join(PROJECT_ROOT, "certs", "server.key")
    os.environ["RELAY_TLS"] = "true"


def _reload_config():
    import config
    importlib.reload(config)
    return config


@pytest_asyncio.fixture(scope="session")
async def mock_llm():
    from mock_llm import handle_chat, handle_models

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat)
    app.router.add_post("/anthropic/v1/messages", handle_chat)
    app.router.add_get("/v1/models", handle_models)

    # Store received headers for test inspection
    received_headers = []

    @web.middleware
    async def capture_headers(request, handler):
        received_headers.append(dict(request.headers))
        return await handler(request)

    app_with_middleware = web.Application(middlewares=[capture_headers])
    app_with_middleware.router.add_post("/v1/chat/completions", handle_chat)
    app_with_middleware.router.add_post("/anthropic/v1/messages", handle_chat)
    app_with_middleware.router.add_get("/v1/models", handle_models)
    app_with_middleware["received_headers"] = received_headers

    runner = web.AppRunner(app_with_middleware)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    app_with_middleware["port"] = port

    yield app_with_middleware

    await runner.cleanup()


@pytest_asyncio.fixture(scope="session")
async def relay(mock_llm):
    _ensure_certs()
    mock_llm_port = mock_llm["port"]

    # Find a free port for relay
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    relay_port = sock.getsockname()[1]
    sock.close()

    _setup_env(mock_llm_port, relay_port)
    _reload_config()

    import relay_server
    importlib.reload(relay_server)

    app = relay_server.create_app()
    relay_instance = None
    for resource in app.router.resources():
        pass
    # Get the RelayServer instance from the app's routes
    for route in app.router.routes():
        handler = route.handler
        if hasattr(handler, "__self__") and isinstance(handler.__self__, relay_server.RelayServer):
            relay_instance = handler.__self__
            break

    # Alternative: create fresh instance and app
    relay_instance = relay_server.RelayServer()
    app = web.Application()
    app.router.add_get("/", relay_instance.handle_index)
    app.router.add_get("/ws/notifications", relay_instance.handle_websocket)
    app.router.add_route("*", "/v1/{path:.*}", relay_instance.handle_api)
    app.router.add_route("*", "/api/{path:.*}", relay_instance.handle_api)
    app.router.add_route("*", "/anthropic/{path:.*}", relay_instance.handle_api)
    app.router.add_route("*", "/{path:.*}", relay_instance.handle_catch_all)

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert_file = os.path.join(PROJECT_ROOT, "certs", "server.crt")
    key_file = os.path.join(PROJECT_ROOT, "certs", "server.key")
    ssl_ctx.load_cert_chain(cert_file, key_file)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", relay_port, ssl_context=ssl_ctx)
    await site.start()

    app["relay_instance"] = relay_instance
    app["port"] = relay_port

    yield app

    await runner.cleanup()


@pytest_asyncio.fixture
async def tunnel(relay):
    """Start tunnel client (C) connecting to relay (B)."""
    _reload_config()

    import _server
    importlib.reload(_server)

    worker = _server.Worker()
    task = asyncio.create_task(worker.start())

    relay_instance = relay["relay_instance"]
    for _ in range(50):
        if relay_instance.tunnel_ws is not None and not relay_instance.tunnel_ws.closed:
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("Tunnel client did not connect within 5s")

    yield worker

    worker._running = False
    if relay_instance.tunnel_ws and not relay_instance.tunnel_ws.closed:
        await relay_instance.tunnel_ws.close()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    if worker.session:
        await worker.session.close()


@pytest_asyncio.fixture
async def full_chain(relay, mock_llm, tunnel):
    """Full chain ready: mock_llm + relay + tunnel all connected."""
    yield {
        "relay": relay,
        "mock_llm": mock_llm,
        "tunnel": tunnel,
        "relay_port": relay["port"],
        "mock_llm_port": mock_llm["port"],
    }


def _client_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@pytest_asyncio.fixture
async def client(relay):
    """HTTP client that trusts self-signed certs."""
    connector = aiohttp.TCPConnector(ssl=_client_ssl_ctx())
    session = aiohttp.ClientSession(connector=connector)
    yield session
    await session.close()
