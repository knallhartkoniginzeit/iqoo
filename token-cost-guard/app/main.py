from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from pathlib import Path
from contextlib import asynccontextmanager
import json
import time
import logging
from datetime import datetime

from app.config import settings, hash_api_key, get_api_key_hash_prefix, BUDGETS
from app.token_counter import get_token_counter, close_token_counter
from app.pricing import calculate_estimated_cost
from app.ledger import ledger
from app.budget import get_budget_for_key, check_budget, format_budget_error
from app.auth import extract_api_key, validate_api_key
from app.security import input_validator, rate_limiter, check_rate_limit
from app.proxy import proxy_request, proxy_request_streaming, close_proxy_client

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEMO_DIR = Path(__file__).parent.parent / "demo"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_token_counter()
    await close_proxy_client()


app = FastAPI(
    title="Token Cost Guard",
    description="Proxy for Anthropic API with token counting and budget enforcement",
    version="1.0.0",
    lifespan=lifespan,
)


def budget_headers(estimated_cost: float, spent_today: float, daily_limit: float) -> Dict[str, str]:
    return {
        "x-tcg-estimated-cost": f"{estimated_cost:.6f}",
        "x-tcg-spent-today": f"{spent_today:.6f}",
        "x-tcg-budget-limit": f"{daily_limit:.2f}",
    }


class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system|tool)$")
    content: Any


class MessageRequest(BaseModel):
    model: str = Field(..., min_length=1)
    messages: List[Message]
    system: Optional[str] = None
    max_tokens: Optional[int] = Field(default=1024, ge=1, le=128000)
    stop_sequences: Optional[List[str]] = None
    temperature: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(default=250, ge=-1)
    metadata: Optional[Dict[str, Any]] = None
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Dict[str, Any]] = None
    parallel_tool_calls: Optional[bool] = None


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "validation_error", "message": "Invalid request body", "details": exc.errors()},
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def demo_page():
    return FileResponse(DEMO_DIR / "frontend.html")


@app.get("/chat-demo")
async def chat_demo_page():
    return FileResponse(DEMO_DIR / "chat_demo.html")


@app.get("/walkthrough")
@app.get("/video")
@app.get("/showcase")
async def showcase_page():
    return FileResponse(DEMO_DIR / "showcase.html")


@app.get("/demo_video.webm")
async def demo_video_file():
    return FileResponse(DEMO_DIR / "demo_video.webm", media_type="video/webm")


@app.get("/walkthrough.webp")
async def walkthrough_file():
    return FileResponse(DEMO_DIR / "walkthrough.webp", media_type="image/webp")


@app.get("/api/summary")
async def api_summary(hours: int = 24):
    hours = max(1, min(hours, 720))
    summary = ledger.get_summary(hours=hours)
    keys = []
    for row in ledger.get_spend_by_key(hours=hours):
        budget = get_budget_for_key(row["api_key_hash"])
        keys.append({
            "key_hash_prefix": row["api_key_hash"][:8],
            "label": budget.get("label", "unknown"),
            "daily_limit_usd": budget.get("daily_limit_usd", 5.0),
            "hard_block": budget.get("hard_block", True),
            "spent_today_usd": round(row.get("spent_today_usd") or 0.0, 6),
            "requests": row.get("request_count", 0),
            "last_activity": row.get("last_activity"),
        })
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "hours": hours,
        "totals": {
            "requests": summary.get("requests", 0),
            "input_tokens": summary.get("input_tokens", 0),
            "output_tokens": summary.get("output_tokens", 0),
            "estimated_cost_usd": round(summary.get("estimated_cost_usd", 0.0), 6),
            "actual_cost_usd": round(summary.get("actual_cost_usd", 0.0), 6),
        },
        "by_model": [
            {
                "model": row.get("model", "unknown"),
                "requests": row.get("request_count", 0),
                "estimated_cost_usd": round(row.get("estimated_cost_usd") or 0.0, 6),
            }
            for row in ledger.get_spend_by_model(hours=hours)
        ],
        "by_key": keys,
    }


@app.get("/api/entries")
async def api_entries(hours: int = 24, limit: int = 50):
    hours = max(1, min(hours, 720))
    limit = max(1, min(limit, 200))
    return {"entries": ledger.get_recent_entries(hours=hours, limit=limit)}


@app.api_route("/v1/messages", methods=["POST"])
async def proxy_messages(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    start_time = time.time()
    api_key = extract_api_key(dict(request.headers))
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "missing_api_key", "message": "x-api-key header required"})
    if not validate_api_key(api_key):
        return JSONResponse(status_code=401, content={"error": "invalid_api_key", "message": "Invalid API key format"})

    api_key_hash = hash_api_key(api_key)
    key_prefix = get_api_key_hash_prefix(api_key)
    logger.info(f"Request received from {key_prefix}...")

    rate_allowed, retry_after = check_rate_limit(api_key_hash)
    if not rate_allowed:
        return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded", "message": "Too many requests", "retry_after": round(retry_after, 2)})

    try:
        body_bytes = await request.body()
        if len(body_bytes) > settings.max_request_size:
            return JSONResponse(status_code=413, content={"error": "request_too_large", "message": f"Request body exceeds {settings.max_request_size} bytes"})
        request_body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        return JSONResponse(status_code=400, content={"error": "invalid_json", "message": str(e)})

    is_valid, error_msg = input_validator.validate_request(request_body)
    if not is_valid:
        logger.warning(f"Invalid request from {key_prefix}...: {error_msg}")
        return JSONResponse(status_code=400, content={"error": "validation_error", "message": error_msg})

    model = request_body.get("model", "")
    is_streaming = request_body.get("stream", False)

    token_counter = get_token_counter()
    try:
        token_result = await token_counter.count_tokens(request_body)
    except Exception as e:
        logger.error(f"Token counting failed: {e}")
        token_result = {"success": False, "error": str(e), "model": model}

    if not token_result.get("success", False):
        if settings.fail_mode == "closed":
            logger.warning(f"Token count failed for {key_prefix}... - blocking")
            return JSONResponse(status_code=503, content={"error": "budget_check_unavailable", "message": "Token counting service unavailable"})
        else:
            logger.warning(f"Token count failed for {key_prefix}... - forwarding anyway")

    estimated_cost = token_result.get("estimated_cost_usd", 0.0)
    input_tokens = token_result.get("input_tokens", 0)
    output_tokens_estimated = token_result.get("output_tokens_estimated")

    logger.info(f"Token count: {input_tokens} input tokens, est. ${estimated_cost:.6f} for {key_prefix}...")

    spent_today = ledger.get_spend_today(api_key_hash)
    budget = get_budget_for_key(api_key_hash)
    daily_limit = budget.get("daily_limit_usd", 5.0)

    budget_decision = check_budget(
        estimated_cost_usd=estimated_cost,
        spent_today_usd=spent_today,
        limit_usd=daily_limit,
    )

    if not budget_decision.allow:
        logger.warning(f"Budget exceeded for {key_prefix}...")
        ledger.create_entry(
            api_key_hash=api_key_hash,
            project=budget.get("label"),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens_estimated,
            estimated_cost_usd=estimated_cost,
            status="blocked",
            error_message=budget_decision.reason,
        )
        return JSONResponse(
            status_code=402,
            content=format_budget_error(budget_decision),
            headers=budget_headers(estimated_cost, spent_today, daily_limit),
        )

    logger.info(f"Budget approved for {key_prefix}...")
    ledger_entry_id = ledger.create_entry(
        api_key_hash=api_key_hash,
        project=budget.get("label"),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens_estimated,
        estimated_cost_usd=estimated_cost,
        status="pending",
    )

    try:
        forward_body = {k: v for k, v in request_body.items() if not k.startswith("extra_")}

        if is_streaming:
            async def stream_response():
                try:
                    async for chunk in proxy_request_streaming(api_key, forward_body, dict(request.headers)):
                        yield chunk
                    ledger.update_entry(entry_id=ledger_entry_id, status="forwarded")
                except Exception as e:
                    logger.error(f"Streaming failed: {e}")
                    ledger.update_entry(entry_id=ledger_entry_id, status="failed", error_message=str(e))
            return StreamingResponse(
                stream_response(),
                status_code=200,
                headers={
                    "content-type": "text/event-stream",
                    **budget_headers(estimated_cost, spent_today, daily_limit),
                },
            )
        else:
            proxy_result = await proxy_request(api_key, forward_body, dict(request.headers))
            actual_cost = None
            if proxy_result.get("status_code") == 200:
                response_body = proxy_result.get("body", {})
                usage = response_body.get("usage", {})
                if usage:
                    actual_input = usage.get("input_tokens", input_tokens)
                    actual_output = usage.get("output_tokens")
                    actual_cost = calculate_estimated_cost(model, actual_input, actual_output)["total_cost_usd"]
                    logger.info(f"Actual cost: ${actual_cost:.6f} USD for {key_prefix}...")
            ledger.update_entry(
                entry_id=ledger_entry_id,
                actual_cost_usd=actual_cost,
                status="forwarded" if proxy_result.get("status_code") == 200 else "failed",
            )
            response_headers = {
                name: value for name, value in proxy_result.get("headers", {}).items()
                if name.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding", "content-type")
            }
            response_headers.update(budget_headers(estimated_cost, spent_today, daily_limit))
            return Response(
                content=json.dumps(proxy_result.get("body", {})),
                status_code=proxy_result.get("status_code", 502),
                headers=response_headers,
                media_type="application/json",
            )
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        ledger.update_entry(entry_id=ledger_entry_id, status="failed", error_message=str(e))
        return JSONResponse(status_code=502, content={"error": "proxy_error", "message": str(e)})
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Request completed in {elapsed:.3f}s for {key_prefix}...")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Token Cost Guard on {settings.proxy_host}:{settings.proxy_port}")
    logger.info(f"Fail mode: {settings.fail_mode}")
    logger.info(f"Budget limits: default ${BUDGETS.get('defaults', {}).get('daily_limit_usd', 5.0)}/day")
    uvicorn.run("app.main:app", host=settings.proxy_host, port=settings.proxy_port, reload=True)
