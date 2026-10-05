# Token Cost Guard

A proxy server that sits between your application and the Anthropic API. It counts tokens before forwarding requests, estimates costs, enforces budgets, and blocks over-budget requests.

## How It Works

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ Your App    │────▶│ Token Cost Guard     │────▶│ Anthropic API       │
│ (SDK)       │     │ (this proxy)         │     │ (api.anthropic.com) │
└─────────────┘     └──────────────────────┘     └─────────────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │ SQLite Ledger │
                   │ (tracks cost) │
                   └───────────────┘
```

### Request Flow

1. **Receive Request** - Your app sends a request to `http://localhost:8000/v1/messages`
2. **Validate** - Check API key format and request schema
3. **Rate Limit** - Prevent abuse with token bucket rate limiting
4. **Count Tokens** - Call Anthropic's free `/v1/messages/count_tokens` endpoint
5. **Estimate Cost** - Look up model pricing and calculate estimated cost
6. **Check Budget** - Compare estimated cost + today's spend against daily limit
7. **Allow or Block**:
   - If over budget: Return 402 with error details
   - If under budget: Forward to Anthropic, record in ledger
8. **Stream or Forward** - Return response (streaming or single response)

## Quick Start

```bash
cd token-cost-guard

# 1. Create .env file with your API key
cp .env.example .env
# Edit .env and add your Anthropic API key

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
python -m app.main

# 4. Point your SDK at the proxy
# Python:
from anthropic import Anthropic
client = Anthropic(base_url="http://localhost:8000", api_key="your-key")

# Node.js:
import Anthropic from '@anthropic-ai/sdk';
const client = new Anthropic({ baseURL: 'http://localhost:8000' });
```

## Configuration

### `.env` File
```env
ANTHROPIC_API_KEY=sk-ant-api01-...
PROXY_HOST=0.0.0.0
PROXY_PORT=8000
FAIL_MODE=closed
LOG_LEVEL=INFO
```

### `config/budgets.yaml`
```yaml
budgets:
  - key_hash_prefix: "abc12345"
    label: "dev-team"
    daily_limit_usd: 20.00
    hard_block: true

defaults:
  daily_limit_usd: 5.00
  hard_block: true
```

## Demo (no real API key needed)

The bundled demo UI is served by the proxy itself at `http://localhost:8000/`.

```bash
cd token-cost-guard

# 1. Start the mock Anthropic upstream (port 8001)
python demo/mock_anthropic.py &

# 2. Point the proxy at the mock and start it (port 8000)
ANTHROPIC_API_KEY=sk-ant-api01-demo-server-key ANTHROPIC_BASE_URL=http://127.0.0.1:8001 \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Open http://localhost:8000/ and click through the demo scenarios
#    (health check, allowed request, 402 over-budget block, 401 invalid key, 429 flood)
```

To re-record the demo video (requires `.venv` with playwright, e.g. `python -m venv .venv && .venv/Scripts/pip install playwright && .venv/Scripts/python -m playwright install ffmpeg`):

```bash
.venv/Scripts/python demo/record_demo.py   # writes demo/demo_video.webm
```

## Side-by-side Dashboard (browser extension)

A Manifest V3 browser extension that opens a live side panel showing spend, budgets, and the request ledger alongside your app. It polls the proxy's JSON API (`/api/summary`, `/api/entries`) — no server needed.

### Install (Chrome / Edge)

1. Start the proxy: `python -m app.main` (port 8000).
2. Open `chrome://extensions` (or `edge://extensions`).
3. Enable **Developer mode**.
4. Click **Load unpacked** and select `token-cost-guard/extension`.
5. Click the extension toolbar icon; the side panel opens.

### Run it

```bash
cd token-cost-guard

# 1. Start the mock upstream (for demo)
python demo/mock_anthropic.py &

# 2. Start the proxy
ANTHROPIC_API_KEY=sk-ant-api01-demo-server-key ANTHROPIC_BASE_URL=http://127.0.0.1:8001 \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Open the side panel (chrome://extensions -> Details -> Service worker -> inspect)
```

The side panel shows:

- **Totals** — spent today, request count, estimated cost.
- **Budgets** — a per-key bar showing today's spend vs. daily limit (green/yellow/red).
- **By Model** — spend grouped by model.
- **Recent Requests** — a compact ledger of the last requests with status chips.
- **Connection status** — live dot; green = proxy reachable, red = offline.
- **Refresh interval** — configurable on the settings page (opened via the gear icon or the footer link).

### API the dashboard polls

| Endpoint | Description |
|----------|-------------|
| `GET /api/summary?hours=N` | Totals, by model, and per-key spend/budget. |
| `GET /api/entries?hours=N&limit=K` | Recent ledger entries. |

### Re-record the side-by-side demo

```bash
.venv/Scripts/python demo/record_demo.py   # writes demo/demo_video.webm
```

## CLI Reports

```bash
# Summary of all spend
python -m app.report summary --since 24

# Spend by model
python -m app.report spend --since 24

# Detailed spend for a key
python -m app.report key --since 24 --key abc12345
```

## Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check |
| `/v1/messages` | POST | Yes | Proxy to Anthropic |

## Error Responses

| Status | Error | Description |
|--------|-------|-------------|
| 401 | missing_api_key | No API key provided |
| 401 | invalid_api_key | Invalid API key format |
| 402 | budget_exceeded | Request would exceed budget |
| 429 | rate_limit_exceeded | Too many requests |
| 503 | budget_check_unavailable | Token counting failed, fail_mode=closed |
