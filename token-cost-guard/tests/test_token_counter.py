import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.token_counter import TokenCounter, count_tokens


class TestTokenCounter:
    @pytest.mark.asyncio
    async def test_count_tokens_success(self):
        counter = TokenCounter()
        mock_response = MagicMock()
        mock_response.json.return_value = {"input_tokens": 100}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch.object(counter, '_get_client', new_callable=AsyncMock, return_value=mock_client):
            result = await counter.count_tokens({
                "model": "claude-3-haiku-20240307",
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert result["success"] is True
        assert result["input_tokens"] == 100
        assert "estimated_cost_usd" in result

    @pytest.mark.asyncio
    async def test_count_tokens_timeout(self):
        counter = TokenCounter()
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Timeout")

        with patch.object(counter, '_get_client', new_callable=AsyncMock, return_value=mock_client):
            result = await counter.count_tokens({
                "model": "claude-3-haiku-20240307",
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert result["success"] is False
        assert result["error"] == "Timeout"
        assert result["input_tokens"] == 0

    @pytest.mark.asyncio
    async def test_count_tokens_http_error(self):
        counter = TokenCounter()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 not found")
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(counter, '_get_client', new_callable=AsyncMock, return_value=mock_client):
            result = await counter.count_tokens({
                "model": "claude-3-haiku-20240307",
                "messages": [{"role": "user", "content": "Hello"}],
            })

        assert result["success"] is False
        assert "error" in result

    def test_convenience_function(self):
        assert callable(count_tokens)


class TestPricing:
    def test_calculate_estimated_cost(self):
        from app.pricing import calculate_estimated_cost

        cost = calculate_estimated_cost(
            model="claude-3-haiku-20240307",
            input_tokens=1000,
            max_tokens=500,
        )

        assert "input_cost_usd" in cost
        assert "output_cost_usd" in cost
        assert "total_cost_usd" in cost

        expected_input = (1000 / 1_000_000) * 0.25
        expected_output = (500 / 1_000_000) * 1.25

        assert abs(cost["input_cost_usd"] - expected_input) < 0.0001
        assert abs(cost["output_cost_usd"] - expected_output) < 0.0001

    def test_calculate_cost_unknown_model(self):
        from app.pricing import calculate_estimated_cost
        cost = calculate_estimated_cost(
            model="unknown-model-2024",
            input_tokens=1000,
        )
        assert cost["total_cost_usd"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
