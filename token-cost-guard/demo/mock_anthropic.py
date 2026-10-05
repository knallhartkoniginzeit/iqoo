import asyncio
import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock Anthropic API")


def estimate_input_tokens(body: dict) -> int:
    text = json.dumps(body.get("messages", []))
    if body.get("system"):
        text += body["system"]
    return max(1, len(text) // 4)


def mock_output_tokens(body: dict) -> int:
    return min(180, max(1, body.get("max_tokens", 256) // 8))


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    body = await request.json()
    if not request.headers.get("x-api-key"):
        return JSONResponse(status_code=401, content={"error": "missing api key"})
    return {"input_tokens": estimate_input_tokens(body)}


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    input_tokens = estimate_input_tokens(body)
    output_tokens = mock_output_tokens(body)
    reply = (
        "A proxy server is an intermediary that sits between a client and a backend "
        "service, forwarding requests and responses while adding policy, logging, or "
        "caching along the way."
    )

    if body.get("stream"):
        async def sse():
            events = [
                ("message_start", {"type": "message_start", "message": {
                    "id": "msg_mock_001", "type": "message", "role": "assistant",
                    "model": body.get("model", "claude-3-mock"),
                    "usage": {"input_tokens": input_tokens, "output_tokens": 1},
                }}),
                ("content_block_start", {"type": "content_block_start", "index": 0,
                                          "content_block": {"type": "text", "text": ""}}),
                ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                          "delta": {"type": "text_delta", "text": reply}}),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                ("message_delta", {"type": "message_delta",
                                    "delta": {"stop_reason": "end_turn"},
                                    "usage": {"output_tokens": output_tokens}}),
                ("message_stop", {"type": "message_stop"}),
            ]
            for name, payload in events:
                yield f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode()
                await asyncio.sleep(0.05)

        return StreamingResponse(sse(), media_type="text/event-stream")

    return {
        "id": "msg_mock_001",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "claude-3-mock"),
        "content": [{"type": "text", "text": reply}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
