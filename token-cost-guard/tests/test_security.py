import pytest
import time
from app.security import RateLimiter, InputValidator, check_rate_limit
from app.auth import extract_api_key, validate_api_key


class TestRateLimiter:
    def test_allows_within_rate_limit(self):
        limiter = RateLimiter(rate=10.0, burst=5)
        for i in range(5):
            assert limiter.is_allowed("test-key") is True

    def test_blocks_after_burst_exhausted(self):
        limiter = RateLimiter(rate=10.0, burst=3)
        for i in range(3):
            limiter.is_allowed("test-key")
        assert limiter.is_allowed("test-key") is False

    def test_refills_over_time(self):
        limiter = RateLimiter(rate=10.0, burst=2)
        limiter.is_allowed("test-key")
        limiter.is_allowed("test-key")
        assert limiter.is_allowed("test-key") is False
        time.sleep(0.25)
        assert limiter.is_allowed("test-key") is True

    def test_different_keys_independent(self):
        limiter = RateLimiter(rate=10.0, burst=2)
        limiter.is_allowed("key1")
        limiter.is_allowed("key1")
        assert limiter.is_allowed("key1") is False
        assert limiter.is_allowed("key2") is True


class TestInputValidator:
    def test_valid_request(self):
        validator = InputValidator()
        request = {
            "model": "claude-3-haiku-20240307",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 1000,
        }
        is_valid, error = validator.validate_request(request)
        assert is_valid is True
        assert error is None

    def test_missing_messages(self):
        validator = InputValidator()
        request = {
            "model": "claude-3-haiku-20240307",
        }
        is_valid, error = validator.validate_request(request)
        assert is_valid is False
        assert error is not None

    def test_invalid_role(self):
        validator = InputValidator()
        request = {
            "model": "claude-3-haiku-20240307",
            "messages": [
                {"role": "invalid-role", "content": "Hello"}
            ],
        }
        is_valid, error = validator.validate_request(request)
        assert is_valid is False

    def test_missing_role(self):
        validator = InputValidator()
        request = {
            "model": "claude-3-haiku-20240307",
            "messages": [
                {"content": "Hello"}
            ],
        }
        is_valid, error = validator.validate_request(request)
        assert is_valid is False
        assert "role" in error.lower()

    def test_invalid_max_tokens(self):
        validator = InputValidator()
        request = {
            "model": "claude-3-haiku-20240307",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": -1,
        }
        is_valid, error = validator.validate_request(request)
        assert is_valid is False

    def test_temperature_validation(self):
        validator = InputValidator()
        request = {
            "model": "claude-3-haiku-20240307",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 1.5,
        }
        is_valid, _ = validator.validate_request(request)
        assert is_valid is True

        request["temperature"] = 2.5
        is_valid, error = validator.validate_request(request)
        assert is_valid is False


class TestAuthUtils:
    def test_extract_api_key_from_header(self):
        headers = {"x-api-key": "sk-ant-api01-test-key"}
        key = extract_api_key(headers)
        assert key == "sk-ant-api01-test-key"

    def test_extract_api_key_from_authorization(self):
        headers = {"authorization": "Bearer sk-ant-api01-test-key"}
        key = extract_api_key(headers)
        assert key == "sk-ant-api01-test-key"

    def test_validate_api_key_format(self):
        assert validate_api_key("sk-ant-api01-valid-key") is True
        assert validate_api_key("invalid-key") is False
        assert validate_api_key(None) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
