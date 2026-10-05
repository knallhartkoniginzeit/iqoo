from typing import Dict, Optional
from app.config import PRICES


def get_model_price(model: str) -> Optional[Dict[str, float]]:
    return PRICES.get(model)


def calculate_estimated_cost(model: str, input_tokens: int, max_tokens: Optional[int] = None) -> Dict[str, float]:
    prices = get_model_price(model)
    if prices is None:
        return {"input_cost_usd": 0.0, "output_cost_usd": 0.0, "total_cost_usd": 0.0}
    input_cost = (input_tokens / 1_000_000) * prices["input_per_mtok"]
    output_cost = (max_tokens / 1_000_000) * prices["output_per_mtok"] if max_tokens else 0.0
    return {"input_cost_usd": round(input_cost, 6), "output_cost_usd": round(output_cost, 6), "total_cost_usd": round(input_cost + output_cost, 6)}


def format_cost(cost_usd: float) -> str:
    if cost_usd < 0.01:
        return f"${cost_usd:.6f}"
    elif cost_usd < 1.00:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"
