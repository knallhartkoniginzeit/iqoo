import re
from typing import Dict, Any, Optional, Tuple


def validate_api_key(api_key: Optional[str]) -> bool:
    if not api_key:
        return False
    pattern = r"^sk-ant-api\d+-[a-zA-Z0-9_-]+$"
    return bool(re.match(pattern, api_key))


def extract_api_key(headers: Dict[str, str]) -> Optional[str]:
    if "x-api-key" in headers:
        return headers["x-api-key"]
    auth = headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def redact_api_key(api_key: str) -> str:
    if not api_key or len(api_key) < 8:
        return "****"
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
