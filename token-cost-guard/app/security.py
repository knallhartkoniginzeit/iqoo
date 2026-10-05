import time
import threading
from typing import Dict, Any, Optional, Tuple
from app.auth import validate_api_key, extract_api_key


class RateLimiter:
    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate
        self.burst = burst
        self._buckets: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> Dict[str, float]:
        if key not in self._buckets:
            self._buckets[key] = {"tokens": self.burst, "last_update": time.time()}
        return self._buckets[key]

    def is_allowed(self, key: str) -> bool:
        with self._lock:
            bucket = self._get_bucket(key)
            now = time.time()
            elapsed = now - bucket["last_update"]
            bucket["tokens"] = min(self.burst, bucket["tokens"] + elapsed * self.rate)
            bucket["last_update"] = now
            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True
            return False

    def get_retry_after(self, key: str) -> float:
        with self._lock:
            bucket = self._get_bucket(key)
            if bucket["tokens"] >= 1:
                return 0.0
            return (1 - bucket["tokens"]) / self.rate


class InputValidator:
    ALLOWED_FIELDS = {
        "model", "messages", "system", "max_tokens", "stop_sequences",
        "temperature", "top_p", "top_k", "metadata", "stream",
        "tools", "tool_choice", "parallel_tool_calls",
        "extra_headers", "extra_query", "extra_body",
    }

    def validate_message(self, message: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if not isinstance(message, dict):
            return False, "Message must be an object"
        if "role" not in message:
            return False, "Message must have 'role' field"
        if message["role"] not in ("user", "assistant", "system", "tool"):
            return False, f"Invalid role: {message['role']}"
        if "content" not in message:
            return False, "Message must have 'content' field"
        return True, None

    def validate_request(self, request: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        for key in request:
            if key not in self.ALLOWED_FIELDS:
                if not key.startswith("extra_"):
                    return False, f"Unexpected field: {key}"
        if "messages" not in request:
            return False, "messages is required"
        if "model" not in request:
            return False, "model is required"
        messages = request["messages"]
        if not isinstance(messages, list) or len(messages) == 0:
            return False, "messages must be a non-empty array"
        for i, msg in enumerate(messages):
            valid, error = self.validate_message(msg)
            if not valid:
                return False, f"messages[{i}]: {error}"
        if "max_tokens" in request:
            max_tokens = request["max_tokens"]
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                return False, "max_tokens must be a positive integer"
        if "model" in request:
            model = request["model"]
            if not isinstance(model, str) or not model:
                return False, "model must be a non-empty string"
        if "temperature" in request:
            temp = request["temperature"]
            if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                return False, "temperature must be between 0 and 2"
        if "stream" in request:
            stream = request["stream"]
            if not isinstance(stream, bool):
                return False, "stream must be a boolean"
        return True, None


rate_limiter = RateLimiter(rate=10.0, burst=20)
input_validator = InputValidator()


def check_rate_limit(api_key_hash: str) -> Tuple[bool, Optional[float]]:
    if rate_limiter.is_allowed(api_key_hash):
        return True, None
    return False, rate_limiter.get_retry_after(api_key_hash)
