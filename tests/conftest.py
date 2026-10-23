import socket
import threading
import time

import pytest
import uvicorn

from authscope.http_engine import SecretStore


@pytest.fixture(scope="session")
def demo_url():
    from demo_api.app import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def demo_secrets():
    from demo_api.fixtures import TOKENS

    store = SecretStore()
    for name, token in TOKENS.items():
        store.set("p", name, token)
    return store


@pytest.fixture(autouse=True)
def _reset_demo_state():
    from demo_api.app import reset_state

    reset_state()
