import os
import yaml
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Optional
import hashlib


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_base_url: str = Field(default="https://api.anthropic.com")
    proxy_host: str = Field(default="0.0.0.0")
    proxy_port: int = Field(default=8000)
    secret_key: str = Field(default="dev-secret-key-change-me-in-production")
    log_level: str = Field(default="INFO")
    fail_mode: str = Field(default="closed")
    max_request_size: int = Field(default=10 * 1024 * 1024)


settings = Settings()


def load_prices() -> Dict[str, Dict[str, float]]:
    prices_path = Path(__file__).parent.parent / "config" / "prices.yaml"
    try:
        with open(prices_path, "r") as f:
            data = yaml.safe_load(f)
            return data.get("models", {})
    except FileNotFoundError:
        return {
            "claude-3-5-sonnet-20241022": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
            "claude-3-5-sonnet-20240620": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
            "claude-3-opus-20240229": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
            "claude-3-haiku-20240307": {"input_per_mtok": 0.25, "output_per_mtok": 1.25},
            "claude-2.1": {"input_per_mtok": 8.00, "output_per_mtok": 24.00},
            "claude-2.0": {"input_per_mtok": 8.00, "output_per_mtok": 24.00},
        }


def load_budgets() -> Dict[str, Any]:
    budgets_path = Path(__file__).parent.parent / "config" / "budgets.yaml"
    try:
        with open(budgets_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {"budgets": [], "defaults": {"daily_limit_usd": 5.00, "hard_block": True}}


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_api_key_hash_prefix(api_key: str, length: int = 8) -> str:
    return hash_api_key(api_key)[:length]


PRICES = load_prices()
BUDGETS = load_budgets()
