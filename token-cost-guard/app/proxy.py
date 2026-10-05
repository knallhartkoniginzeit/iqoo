import httpx
from typing import Dict, Any, Optional, AsyncGenerator
from app.config import settings
import logging

logger = logging.getLogger(__name__)

HOP_BY_HOP_HEADERS = {
    "host", "content-length", "content-encoding", "transfer-encoding",
    "connection", "keep-alive", "upgrade", "proxy-authorization",
    "proxy-authenticate", "te", "trailer",
}


def forwardable_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        name: value for name, value in headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS
    }


class ProxyClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=settings.anthropic_base_url, timeout=300.0)
        return self._client

    async def forward_request(
        self, original_api_key: str, request_body: Dict[str, Any], headers: Dict[str, str]
    ) -> Dict[str, Any]:
        client = await self._get_client()
        try:
            response = await client.post(
                "/v1/messages",
                json=request_body,
                headers={
                    "x-api-key": original_api_key,
                    "anthropic-version": "2023-06-01",
                    **forwardable_headers(headers),
                },
            )
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.json(),
            }
        except httpx.TimeoutException:
            return {"status_code": 504, "headers": {}, "body": {"error": "Gateway timeout"}}
        except httpx.HTTPStatusError as e:
            return {
                "status_code": e.response.status_code,
                "headers": dict(e.response.headers),
                "body": e.response.json(),
            }
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return {"status_code": 502, "headers": {}, "body": {"error": f"Bad gateway: {str(e)}"}}

    async def forward_request_streaming(
        self, original_api_key: str, request_body: Dict[str, Any], headers: Dict[str, str]
    ) -> AsyncGenerator[bytes, None]:
        client = await self._get_client()
        try:
            async with client.stream(
                "POST",
                "/v1/messages",
                json=request_body,
                headers={
                    "x-api-key": original_api_key,
                    "anthropic-version": "2023-06-01",
                    **forwardable_headers(headers),
                },
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk
        except Exception as e:
            logger.error(f"Proxy streaming error: {e}")
            yield f'{{"error": "Bad gateway: {str(e)}"}}\n'.encode()

    async def close(self):
        if self._client is not None:
            await self._client.aclose()


async def proxy_request(original_api_key: str, request_body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    return await get_proxy_client().forward_request(original_api_key, request_body, headers)


async def proxy_request_streaming(
    original_api_key: str, request_body: Dict[str, Any], headers: Dict[str, str]
) -> AsyncGenerator[bytes, None]:
    async for chunk in get_proxy_client().forward_request_streaming(original_api_key, request_body, headers):
        yield chunk


_shared_client: Optional[ProxyClient] = None


def get_proxy_client() -> ProxyClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = ProxyClient()
    return _shared_client


async def close_proxy_client() -> None:
    global _shared_client
    if _shared_client is not None:
        await _shared_client.close()
        _shared_client = None
