"""The CI gate script itself, run against two in-process demo instances."""
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
DEMO_PROCESS = """
import os, sys
os.environ["DEMO_VULNS"] = sys.argv[1]
sys.path.insert(0, sys.argv[3])
import uvicorn
from demo_api.app import app
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="error")
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def two_demos():
    """Separate processes: the vulnerability switch is read from each process's environment."""
    procs, urls = [], []
    for vulns in ("", "bola,bfla,bopla,unauth,tenant"):
        port = free_port()
        procs.append(subprocess.Popen([sys.executable, "-c", DEMO_PROCESS, vulns, str(port), str(ROOT / "backend")]))
        urls.append(f"http://127.0.0.1:{port}")
    for url in urls:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
    yield urls
    for p in procs:
        p.terminate()
        p.wait(timeout=10)


def test_gate_passes_on_secure_and_vulnerable_demo(two_demos, tmp_path):
    secure, vulnerable = two_demos
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "ci_gate.py"), "--secure", secure,
                          "--vulnerable", vulnerable, "--out", str(tmp_path)], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "GATE PASSED" in out.stdout
    assert (tmp_path / "vulnerable.html").exists() and (tmp_path / "secure.md").exists()


def test_gate_fails_when_the_vulnerable_side_looks_secure(two_demos, tmp_path):
    secure, _ = two_demos
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "ci_gate.py"), "--secure", secure,
                          "--vulnerable", secure], capture_output=True, text=True, timeout=300)
    assert out.returncode == 1 and "missed (false negative)" in out.stdout


_unused = (threading, uvicorn)
