import httpx
from typing import Dict, Any, Optional
from app.config import settings
from app.pricing import calculate_estimated_cost


class TokenCounter:
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=settings.anthropic_base_url,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=30.0,
            )
        return self.client

    async def count_tokens(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        client = await self._get_client()
        try:
            response = await client.post("/v1/messages/count_tokens", json=request_body)
            response.raise_for_status()
            result = response.json()
            input_tokens = result.get("input_tokens", 0)
            model = request_body.get("model", "")
            max_tokens = request_body.get("max_tokens")
            cost = calculate_estimated_cost(model, input_tokens, max_tokens)
            return {
                "input_tokens": input_tokens,
                "output_tokens_estimated": max_tokens,
                "estimated_cost_usd": cost["total_cost_usd"],
                "model": model,
                "success": True,
            }
        except Exception as e:
            return {
                "input_tokens": 0,
                "output_tokens_estimated": 0,
                "estimated_cost_usd": 0.0,
                "model": request_body.get("model", ""),
                "success": False,
                "error": str(e),
            }

    async def close(self):
        if self.client is not None:
            await self.client.aclose()


async def count_tokens(request_body: Dict[str, Any]) -> Dict[str, Any]:
    counter = TokenCounter()
    try:
        return await counter.count_tokens(request_body)
    finally:
        await counter.close()


_shared_counter: Optional[TokenCounter] = None


def get_token_counter() -> TokenCounter:
    global _shared_counter
    if _shared_counter is None:
        _shared_counter = TokenCounter()
    return _shared_counter


async def close_token_counter() -> None:
    global _shared_counter
    if _shared_counter is not None:
        await _shared_counter.close()
        _shared_counter = None
