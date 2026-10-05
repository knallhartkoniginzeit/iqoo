import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
VIDEO_PATH = Path(__file__).parent / "demo_video.webm"
PROXY_URL = "http://localhost:8000/"

conn = sqlite3.connect(ROOT / "ledger.db")
conn.execute("DELETE FROM usage")
conn.commit()
conn.close()

with tempfile.TemporaryDirectory() as video_dir:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            record_video_dir=video_dir,
            record_video_size={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.set_default_timeout(30_000)

        page.goto(PROXY_URL)
        page.wait_for_selector("text=Connected")
        page.wait_for_timeout(1500)

        def run_scenario(label: str, button_text: str, wait_text: str, pause_ms: int = 1800):
            page.click(f"button:has-text('{button_text}')")
            page.wait_for_selector(f"text={wait_text}")
            page.wait_for_timeout(pause_ms)

        run_scenario("health check", "Health Check", "healthy", 1500)
        run_scenario("allowed request", "Allowed Request", "msg_mock_001", 2200)
        run_scenario("budget block", "Over Budget (402)", "budget_exceeded", 2500)
        run_scenario("invalid key", "Invalid Key (401)", "invalid_api_key", 1800)
        run_scenario("rate limit flood", "Rate Limit Flood (429)", "Status codes returned", 2500)

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        video = page.video
        context.close()
        browser.close()

        raw = video.path()
        shutil.move(raw, VIDEO_PATH)
