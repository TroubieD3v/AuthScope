"""Browser test of the main workflow: demo project -> run -> matrix -> findings.

Needs `pip install playwright pytest-playwright && playwright install chromium` and a built UI
(`cd frontend && npm run build`). Skipped otherwise.
"""
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

playwright = pytest.importorskip("playwright.sync_api")
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not (DIST / "index.html").exists(), reason="frontend not built")]


@pytest.fixture(scope="module")
def app_url(tmp_path_factory):
    from authscope.api import create_app
    from authscope.storage import Store

    app = create_app(Store(str(tmp_path_factory.mktemp("db") / "ui.db")))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def test_demo_workflow_in_browser(app_url, demo_url, page, monkeypatch):
    monkeypatch.delenv("DEMO_VULNS", raising=False)
    page.set_viewport_size({"width": 1400, "height": 1000})
    page.goto(app_url)

    page.get_by_label("Demo API address").fill(demo_url)
    page.get_by_role("button", name="Load demo project").click()
    page.get_by_text("Test identities").wait_for()

    page.get_by_role("button", name="Test Runner").click()
    page.get_by_role("button", name="Start run (6)").click()
    page.get_by_role("button", name="Open findings").wait_for(timeout=30_000)
    assert "32 violations" in page.text_content("main")

    page.get_by_role("button", name="Permission Matrix").click()
    page.get_by_text("VIOLATION").first.wait_for()
    assert page.get_by_text("VIOLATION").count() >= 10

    page.get_by_role("button", name="Findings & Reports").click()
    page.get_by_text("Policy violation").first.click()
    page.get_by_text("Expected policy", exact=True).wait_for()
    body = page.text_content("main")
    assert "Reproduce" in body and "REDACTED" in body and "demo-bob-" not in body
