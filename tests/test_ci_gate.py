"""The CI gate script itself, run against secure and flawed instances of both test stands."""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STAND_PROCESS = """
import os, sys
os.environ[sys.argv[1]] = sys.argv[2]
sys.path.insert(0, sys.argv[5])
import importlib, uvicorn
app = importlib.import_module(sys.argv[3]).app
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[4]), log_level="error")
"""
STANDS = {
    # stand: (module, flaw switch variable, all flaws)
    "demo": ("demo_api.app", "DEMO_VULNS", "bola,bfla,bopla,unauth,tenant"),
    "ledger": ("ledger_api.app", "LEDGER_FLAWS", "bola,bfla,bopla,tenant"),
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(port: int) -> None:
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)


@pytest.fixture(scope="module", params=sorted(STANDS))
def stand(request):
    """Secure and flawed instance in separate processes (the switch is read from each process's environment)."""
    module, var, all_flaws = STANDS[request.param]
    procs, urls = [], []
    for flaws in ("", all_flaws):
        port = free_port()
        procs.append(subprocess.Popen([sys.executable, "-c", STAND_PROCESS, var, flaws, module, str(port),
                                       str(ROOT / "backend")]))
        urls.append(f"http://127.0.0.1:{port}")
    for url in urls:
        wait_for(int(url.rsplit(":", 1)[1]))
    yield request.param, urls
    for p in procs:
        p.terminate()
        p.wait(timeout=10)


def gate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "ci_gate.py"), *args],
                          capture_output=True, text=True, timeout=300)


def test_gate_passes_on_secure_and_flawed_instance(stand, tmp_path):
    name, (secure, flawed) = stand
    out = gate("--stand", name, "--secure", secure, "--vulnerable", flawed, "--out", str(tmp_path))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "GATE PASSED" in out.stdout
    prefix = "" if name == "demo" else f"{name}-"
    assert (tmp_path / f"{prefix}vulnerable.html").exists() and (tmp_path / f"{prefix}secure.md").exists()


def test_gate_fails_when_the_flawed_side_looks_secure(stand):
    name, (secure, _) = stand
    out = gate("--stand", name, "--secure", secure, "--vulnerable", secure)
    assert out.returncode == 1 and "missed (false negative)" in out.stdout
