"""#6: rate limits, retries and unavailable targets."""
import ipaddress
import socket

import httpx
import pytest

from authscope.compare import classify
from authscope.config import Identity, TargetConfig
from authscope.demo import demo_config
from authscope.http_engine import Requester, retry_after
from authscope.runner import TestRunner


@pytest.fixture()
def instant_sleep(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("authscope.http_engine._sleep", fake_sleep)
    return slept


def requester(handler, **target) -> Requester:
    cfg = TargetConfig(base_url="http://api.example.test", allowed_hosts=["api.example.test"], **target)
    req = Requester(cfg, lambda i: None)

    async def dns(url):
        return [ipaddress.ip_address("198.51.100.20")]

    req.guard.check_resolved = dns  # type: ignore[method-assign]
    req._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return req


def test_retry_after_parsing():
    assert retry_after("3") == 3.0
    assert retry_after(None) == 1.0
    assert retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0  # date in the past
    assert retry_after("soon") == 1.0


async def test_429_is_retried_after_retry_after(instant_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"id": 1})

    req = requester(handler)
    raw = await req.send("GET", "/x")
    assert raw.status == 200 and raw.attempts == 2
    assert req.retries == 1 and instant_sleep == [2.0] and req.budget.used == 2


async def test_long_retry_after_is_not_waited_for_and_stays_inconclusive(instant_sleep):
    req = requester(lambda r: httpx.Response(429, headers={"Retry-After": "3600"}))
    raw = await req.send("GET", "/x")
    assert raw.status == 429 and req.retries == 0 and instant_sleep == []
    assert classify(raw, resource_id="1").kind == "rate_limited"


async def test_transport_errors_retried_for_reads_but_never_for_writes(instant_sleep):
    def boom(request):
        raise httpx.ConnectError("connection refused", request=request)

    reads = requester(boom, max_retries=2)
    raw = await reads.send("GET", "/x")
    assert raw.error and raw.attempts == 3 and reads.retries == 2

    writes = requester(boom, max_retries=2, allow_mutating=True, acknowledge_no_reset=True)
    raw = await writes.send("PUT", "/x", body={"a": 1})
    assert raw.error and raw.attempts == 1 and writes.retries == 0


async def test_retries_respect_the_request_budget(instant_sleep):
    req = requester(lambda r: httpx.Response(429, headers={"Retry-After": "0"}), max_requests=2, max_retries=5)
    raw = await req.send("GET", "/x")
    assert raw.status == 429 and req.budget.used == 2


async def test_unavailable_target_stops_the_run(instant_sleep):
    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cfg = demo_config(f"http://127.0.0.1:{port}")
    cfg.target.max_retries = 0
    cfg.target.timeout_s = 0.3
    cfg.target.rate_limit_rps = 100
    from authscope.http_engine import SecretStore

    store = SecretStore()
    for name in ("alice", "bob", "carol", "admin"):
        store.set("p", name, "x")
    runner = TestRunner(cfg, store, "p", ["bola"])
    results = await runner.run()
    assert runner.abort_reason and "consecutive transport errors" in runner.abort_reason
    errors = [r for r in results if r.verdict == "error"]
    assert len(errors) == TestRunner.MAX_TRANSPORT_STREAK
    assert any(r.verdict == "skipped" and "target unavailable" in r.message for r in results)


async def test_rate_limited_demo_still_gives_the_same_findings(demo_url, demo_secrets, monkeypatch):
    monkeypatch.delenv("DEMO_VULNS", raising=False)
    monkeypatch.setenv("DEMO_RATE_LIMIT", "3")
    cfg = demo_config(demo_url)
    cfg.target.rate_limit_rps = 100
    runner = TestRunner(cfg, demo_secrets, "p", ["bfla"])
    results = await runner.run()
    assert runner.stats.retries > 0
    bad = {(r.identity, r.endpoint_key) for r in results if r.verdict == "violation"}
    assert ("alice", "GET /api/admin/stats") in bad and not [r for r in results if r.observed == "rate_limited"]


def test_identity_unused_import_guard():
    assert Identity(name="z").token_env == "AUTHSCOPE_TOKEN_Z"
