#!/usr/bin/env python3
"""
Mock LLM server for local testing.
Simulates an OpenAI-compatible /v1/chat/completions endpoint.
"""

import json
import time
import uuid

from aiohttp import web


async def handle_chat(request: web.Request) -> web.StreamResponse:
    body = await request.json()
    messages = body.get("messages", [])
    is_stream = body.get("stream", False)
    model = body.get("model", "mock-model")

    user_msg = messages[-1]["content"] if messages else ""
    reply = f"[Mock LLM] You said: {user_msg}"

    if is_stream:
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
        )
        await response.prepare(request)

        for i, word in enumerate(reply.split()):
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": word + " "}, "finish_reason": None}],
            }
            await response.write(f"data: {json.dumps(chunk)}\n\n".encode())
            import asyncio
            await asyncio.sleep(0.05)

        done_chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        await response.write(f"data: {json.dumps(done_chunk)}\n\n".encode())
        await response.write(b"data: [DONE]\n\n")
        return response
    else:
        result = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        return web.json_response(result)


async def handle_models(request: web.Request) -> web.Response:
    return web.json_response({
        "object": "list",
        "data": [{"id": "mock-model", "object": "model", "owned_by": "local"}],
    })


def main():
    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat)
    app.router.add_get("/v1/models", handle_models)
    print("Mock LLM server on http://127.0.0.1:9000")
    web.run_app(app, host="127.0.0.1", port=9000, print=None)


if __name__ == "__main__":
    main()
