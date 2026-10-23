"""Regenerate the README screenshots and the demo GIF.

    pip install -e ".[dev]" pillow && playwright install chromium
    cd frontend && npm run build && cd ..
    python scripts/screenshots.py

Starts the vulnerable demo API and AuthScope (fresh database) on free ports, runs the demo project
in a real browser and writes PNGs and demo.gif to docs/screenshots/.
"""
from __future__ import annotations

import io
import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from PIL import Image
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
VIEWPORT = {"width": 1440, "height": 900}


def serve(app, preferred: int = 0) -> str:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", preferred))
        except OSError:
            s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}"


def frame(page: Page, frames: list[Image.Image], hold: int = 1) -> None:
    img = Image.open(io.BytesIO(page.screenshot())).convert("RGB").resize((1080, 675), Image.LANCZOS)
    frames.extend([img] * hold)


def main() -> None:
    os.environ.pop("DEMO_VULNS", None)
    from authscope.api import create_app
    from authscope.storage import Store
    from demo_api.app import app as demo_app

    demo = serve(demo_app, 8000)  # nicer URL in the screenshots when the port is free
    db = Path(tempfile.mkdtemp()) / "shots.db"
    ui = serve(create_app(Store(str(db))))
    OUT.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, color_scheme="dark")
        page.goto(ui)
        page.get_by_label("Demo API address").fill(demo)
        page.screenshot(path=OUT / "onboarding.png")
        page.get_by_role("button", name="Load demo project").click()
        page.get_by_text("Test identities").wait_for()

        page.get_by_role("button", name="Test Runner").click()
        page.get_by_role("button", name="Start run (6)").wait_for()
        frame(page, frames, 3)
        page.get_by_role("button", name="Start run (6)").click()
        for _ in range(6):
            time.sleep(0.35)
            frame(page, frames)
        page.get_by_role("button", name="Open findings").wait_for(timeout=30_000)
        page.mouse.wheel(0, 600)
        time.sleep(0.3)
        frame(page, frames, 4)
        page.screenshot(path=OUT / "runner.png")

        page.get_by_role("button", name="Dashboard").click()
        page.get_by_text("Results by module").wait_for()
        time.sleep(0.4)
        page.screenshot(path=OUT / "dashboard.png")

        page.get_by_role("button", name="Permission Matrix").click()
        page.get_by_text("VIOLATION").first.wait_for()
        time.sleep(0.3)
        frame(page, frames, 8)
        page.screenshot(path=OUT / "matrix.png")

        page.get_by_role("button", name="Findings & Reports").click()
        page.get_by_text("Policy violation").first.wait_for()
        row = page.get_by_text("bob -> GET /api/orders/{order_id} [order:101]", exact=True)
        row.scroll_into_view_if_needed()
        row.click()
        page.get_by_text("Expected policy", exact=True).wait_for()
        row.evaluate("e => e.closest('button').scrollIntoView({block: 'start'})")
        time.sleep(0.3)
        frame(page, frames, 10)
        page.screenshot(path=OUT / "findings.png")

        page.get_by_role("button", name="API Explorer").click()
        page.get_by_text("Endpoints (").wait_for()
        page.screenshot(path=OUT / "explorer.png")

        page.get_by_role("button", name="Identity Manager").click()
        page.get_by_text("Test objects and their owners").wait_for()
        page.screenshot(path=OUT / "identities.png")
        browser.close()

    frames[0].save(OUT / "demo.gif", save_all=True, append_images=frames[1:], duration=350, loop=0, optimize=True)
    for f in sorted(OUT.iterdir()):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
