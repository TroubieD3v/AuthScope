"""End-to-end: engine and API against the bundled demo API (vulnerable and secure variants)."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from authscope.api import create_app
from authscope.demo import demo_config
from authscope.runner import TestRunner
from authscope.storage import Store

ALL = ["unauth", "bola", "bfla", "bopla", "tenant", "custom"]


async def run_engine(url, secrets, mutating=False, modules=ALL):
    cfg = demo_config(url)
    cfg.target.allow_mutating = mutating
    cfg.target.rate_limit_rps = 100
    runner = TestRunner(cfg, secrets, "p", modules)
    return await runner.run(), runner


def pick(results, **kw):
    return [r for r in results if all(getattr(r, k) == v for k, v in kw.items())]


async def test_vulnerable_demo_is_fully_detected(demo_url, demo_secrets, monkeypatch):
    monkeypatch.delenv("DEMO_VULNS", raising=False)
    results, runner = await run_engine(demo_url, demo_secrets)
    bad = {(r.module, r.identity, r.endpoint_key, r.resource) for r in results if r.verdict == "violation"}

    assert ("unauth", "guest", "GET /api/reports/summary", None) in bad
    assert ("bola", "bob", "GET /api/orders/{order_id}", "order:101") in bad
    assert ("bola", "bob", "GET /api/orders", None) in bad  # list leak
    assert ("bfla", "alice", "GET /api/admin/stats", None) in bad
    assert ("bopla", "alice", "GET /api/users/{user_id}", "user:1") in bad
    assert ("tenant", "carol", "GET /api/orders/{order_id}", "order:101") in bad
    assert ("tenant", "alice", "GET /api/invoices/{invoice_id}", "invoice:202") in bad
    assert ("custom", "bob", "GET /api/orders/101", "order:101") in bad

    # 200 + [] is filtering, not BOLA
    items = pick(results, endpoint_key="GET /api/orders/{order_id}/items", identity="bob", resource="order:101")
    assert items and all(r.verdict == "pass" and r.observed == "allowed_empty" for r in items)
    # positive controls
    owner = pick(results, module="bola", identity="alice", endpoint_key="GET /api/orders/{order_id}", resource="order:101")
    assert owner[0].verdict == "pass" and owner[0].expected == "allow"
    # state-changing tests are not sent without the explicit mode
    puts = pick(results, endpoint_key="PUT /api/orders/{order_id}")
    assert puts and all(r.verdict == "skipped" for r in puts)
    assert runner.requester.budget.used < 200


async def test_secure_demo_has_no_findings(demo_url, demo_secrets, monkeypatch):
    monkeypatch.setenv("DEMO_VULNS", "")
    results, _ = await run_engine(demo_url, demo_secrets)
    findings = [(r.module, r.name, r.message) for r in results if r.verdict in ("violation", "needs_review")]
    assert findings == []
    assert sum(r.verdict == "pass" for r in results) > 40
    assert not [r for r in results if r.verdict == "error"]


async def test_mutating_mode_detects_writes_and_resets_state(demo_url, demo_secrets, monkeypatch):
    from demo_api import app as demo

    monkeypatch.delenv("DEMO_VULNS", raising=False)
    results, runner = await run_engine(demo_url, demo_secrets, mutating=True)
    bad = {(r.module, r.identity, r.endpoint_key, r.resource) for r in results if r.verdict == "violation"}
    assert ("bola", "bob", "PUT /api/orders/{order_id}", "order:101") in bad
    assert ("bfla", "alice", "DELETE /api/admin/users/{user_id}", "user:1") in bad
    assert demo.ORDERS[101]["status"] == "paid" and len(demo.USERS) == 4  # reset after every write
    assert not [w for w in runner.warnings if "reset" in w]


async def test_secure_demo_writes_are_denied(demo_url, demo_secrets, monkeypatch):
    monkeypatch.setenv("DEMO_VULNS", "")
    results, _ = await run_engine(demo_url, demo_secrets, mutating=True)
    assert [r for r in results if r.verdict in ("violation", "needs_review")] == []
    assert pick(results, endpoint_key="PUT /api/orders/{order_id}", identity="alice", resource="order:101")[0].verdict == "pass"


async def test_evidence_never_contains_tokens(demo_url, demo_secrets, monkeypatch):
    from demo_api.fixtures import TOKENS

    monkeypatch.delenv("DEMO_VULNS", raising=False)
    results, _ = await run_engine(demo_url, demo_secrets)
    blob = json.dumps([r.model_dump() for r in results])
    for token in TOKENS.values():
        assert token not in blob
    bola = pick(results, module="bola", identity="bob", resource="order:101", endpoint_key="GET /api/orders/{order_id}")[0]
    assert "$AUTHSCOPE_TOKEN_BOB" in bola.evidence.reproduction[-1]
    assert bola.evidence.baseline.identity == "alice" and bola.evidence.diff


async def test_missing_credentials_are_skipped_not_failed(demo_url, monkeypatch):
    from authscope.http_engine import SecretStore

    for n in ("ALICE", "BOB", "CAROL", "ADMIN"):
        monkeypatch.delenv(f"AUTHSCOPE_TOKEN_{n}", raising=False)
    cfg = demo_config(demo_url)
    runner = TestRunner(cfg, SecretStore(), "none", ["bola"])
    results = await runner.run()
    assert results and all(r.verdict == "skipped" for r in results)
    assert any("No credential" in w for w in runner.warnings)
    assert any("login for 'carol' skipped" in w for w in runner.warnings)


async def test_login_flow_obtains_token_and_masks_password(demo_url, monkeypatch):
    from authscope.demo import demo_secrets
    from authscope.http_engine import SecretStore
    from demo_api.fixtures import PASSWORDS, TOKENS

    monkeypatch.delenv("DEMO_VULNS", raising=False)
    store = SecretStore()
    for (name, kind), value in demo_secrets().items():
        store.set("p", name, value, kind)
    assert store.get("p", demo_config(demo_url).identity("carol")) is None  # no token: must log in
    results, runner = await run_engine(demo_url, store, modules=["tenant"])
    assert runner._login_tokens == {"carol": TOKENS["carol"]}
    carol = pick(results, identity="carol", endpoint_key="GET /api/orders/{order_id}", resource="order:101")
    assert carol and carol[0].verdict == "violation"
    blob = json.dumps([r.model_dump() for r in results])
    assert TOKENS["carol"] not in blob and PASSWORDS["carol"] not in blob


async def test_failed_login_is_reported(demo_url):
    from authscope.http_engine import SecretStore

    store = SecretStore()
    store.set("p", "carol", "wrong-password", "password")
    runner = TestRunner(demo_config(demo_url), store, "p", ["tenant"])
    await runner.run()
    assert any("login for 'carol' failed: HTTP 401" in w for w in runner.warnings)


async def test_query_and_basic_auth_identities(demo_url, monkeypatch):
    from authscope.http_engine import SecretStore
    from demo_api.fixtures import PASSWORDS, TOKENS

    monkeypatch.delenv("DEMO_VULNS", raising=False)
    cfg = demo_config(demo_url)
    cfg.identity("alice").auth = cfg.identity("alice").auth.model_copy(update={"type": "query", "query_name": "api_key"})
    cfg.identity("bob").auth = cfg.identity("bob").auth.model_copy(update={"type": "basic", "username": "bob"})
    store = SecretStore()
    store.set("p", "alice", TOKENS["alice"])
    store.set("p", "bob", PASSWORDS["bob"])
    store.set("p", "admin", TOKENS["admin"])
    results = await TestRunner(cfg, store, "p", ["bola"]).run()

    bad = {(r.identity, r.endpoint_key, r.resource) for r in results if r.verdict == "violation"}
    assert ("bob", "GET /api/orders/{order_id}", "order:101") in bad
    assert ("bob", "GET /api/users/{user_id}/orders/{order_id}", "order:101") in bad  # nested route
    owner = pick(results, identity="alice", endpoint_key="GET /api/orders/{order_id}", resource="order:101")[0]
    assert owner.verdict == "pass"
    blob = json.dumps([r.model_dump() for r in results])
    assert TOKENS["alice"] not in blob and PASSWORDS["bob"] not in blob
    nested = pick(results, identity="bob", endpoint_key="GET /api/users/{user_id}/orders/{order_id}", resource="order:101")[0]
    assert nested.evidence.test.url.endswith("/api/users/1/orders/101")
    assert '-u "bob:$AUTHSCOPE_TOKEN_BOB"' in nested.evidence.reproduction[-1]
    assert "api_key=$AUTHSCOPE_TOKEN_ALICE" in nested.evidence.reproduction[0]


async def test_hostname_target_is_pinned_and_keeps_host_header(demo_url, demo_secrets, monkeypatch):
    monkeypatch.delenv("DEMO_VULNS", raising=False)
    port = demo_url.rsplit(":", 1)[1]
    cfg = demo_config(f"http://localhost:{port}")
    runner = TestRunner(cfg, demo_secrets, "p", ["bfla"])
    results = await runner.run()
    hit = pick(results, identity="alice", endpoint_key="GET /api/admin/stats")[0]
    assert hit.verdict == "violation" and hit.evidence.test.url.startswith("http://localhost:")


async def test_rate_limit_and_budget(demo_url, demo_secrets):
    cfg = demo_config(demo_url)
    cfg.target.max_requests = 5
    runner = TestRunner(cfg, demo_secrets, "p", ["bola"])
    results = await runner.run()
    assert runner.requester.budget.used == 5
    assert any("budget" in w for w in runner.warnings)
    assert any(r.verdict == "skipped" for r in results)


# ---- HTTP API ---------------------------------------------------------------------------
def wait_done(client, rid, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{rid}").json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_api_workflow_reports_matrix_and_regression_diff(demo_url, monkeypatch):
    with TestClient(create_app(Store(":memory:"))) as client:
        proj = client.post("/api/projects/demo", json={"base_url": demo_url}).json()
        pid = proj["id"]
        assert all(i["has_secret"] for i in proj["identities"])

        monkeypatch.delenv("DEMO_VULNS", raising=False)
        r1 = client.post(f"/api/projects/{pid}/runs", json={"modules": ALL}).json()
        assert client.post(f"/api/projects/{pid}/runs", json={"modules": ALL}).status_code in (202, 409)
        run1 = wait_done(client, r1["id"])
        assert run1["status"] == "completed" and run1["stats"]["by_verdict"]["violation"] > 10

        findings = client.get(f"/api/runs/{r1['id']}/results", params={"only": "findings"}).json()
        assert findings and findings[0]["evidence"]["test"]

        md = client.get(f"/api/runs/{r1['id']}/report", params={"format": "md"}).text
        assert "Findings" in md and "$AUTHSCOPE_TOKEN_BOB" in md and "demo-bob" not in md
        html = client.get(f"/api/runs/{r1['id']}/report", params={"format": "html"}).text
        assert "<html" in html and "demo-bob" not in html
        assert json.loads(client.get(f"/api/runs/{r1['id']}/report").text)["summary"]["verdicts"]["violation"] > 10
        py = client.get(f"/api/runs/{r1['id']}/report", params={"format": "pytest"}).text
        compile(py, "regression_test.py", "exec")
        assert "def test_" in py and "os.environ" in py and "demo-bob" not in py

        matrix = client.get(f"/api/projects/{pid}/matrix").json()
        row = next(r for r in matrix["rows"] if r["endpoint"] == "GET /api/admin/stats")
        assert row["cells"]["alice"]["expected"] == "deny" and row["cells"]["alice"]["worst"] == "violation"
        assert row["cells"]["admin"]["expected"] == "allow" and row["cells"]["admin"]["worst"] == "pass"
        assert row["cells"]["guest"]["worst"] == "pass"

        # "fix" the API, re-run, compare releases
        monkeypatch.setenv("DEMO_VULNS", "")
        r2 = client.post(f"/api/projects/{pid}/runs", json={"modules": ALL}).json()
        run2 = wait_done(client, r2["id"])
        assert run2["stats"]["by_verdict"].get("violation", 0) == 0
        diff = client.get(f"/api/runs/{r2['id']}/diff", params={"against": r1["id"]}).json()
        assert len(diff["fixed"]) > 10 and diff["new"] == [] and diff["unchanged"] == []

        dash = client.get(f"/api/projects/{pid}/dashboard").json()
        assert dash["endpoints"] == 13 and dash["latest_run"]["id"] == r2["id"] and len(dash["history"]) == 2


def test_api_import_openapi_from_allowed_url_only(demo_url):
    with TestClient(create_app(Store(":memory:"))) as client:
        cfg = {"name": "x", "target": {"base_url": demo_url}}
        pid = client.post("/api/projects", json=cfg).json()["id"]
        ok = client.post(f"/api/projects/{pid}/import/openapi", json={"url": f"{demo_url}/openapi.json"})
        assert ok.status_code == 200 and ok.json()["added"] >= 10
        eps = {e["path"] + e["method"]: e for e in client.get(f"/api/projects/{pid}").json()["endpoints"]}
        assert eps["/healthGET"]["access"] == "public"
        assert eps["/api/orders/{order_id}GET"]["access"] == "owner"
        assert eps["/api/admin/statsGET"]["access"] == "roles"

        blocked = client.post(f"/api/projects/{pid}/import/openapi", json={"url": "http://169.254.169.254/spec.json"})
        assert blocked.status_code == 400 and "refused" in blocked.json()["detail"]
        bad = client.post(f"/api/projects/{pid}/import/openapi", json={"content": "just text"})
        assert bad.status_code == 422

        from pathlib import Path
        coll = (Path(__file__).resolve().parents[1] / "examples" / "demo.postman_collection.json").read_text(encoding="utf-8")
        pm = client.post(f"/api/projects/{pid}/import", json={"content": coll})
        assert pm.status_code == 200 and pm.json()["format"] == "Postman collection"
        assert pm.json()["added"] == 1  # only GET /api/orders/{orderId} is new; the rest exists from OpenAPI


def test_api_secrets_are_write_only_and_not_persisted(demo_url):
    store = Store(":memory:")
    with TestClient(create_app(store)) as client:
        cfg = {"name": "x", "target": {"base_url": demo_url}, "identities": [{"name": "zed"}]}
        pid = client.post("/api/projects", json=cfg).json()["id"]
        assert client.put(f"/api/projects/{pid}/identities/zed/secret", json={"token": "super-secret-123"}).status_code == 204
        proj = client.get(f"/api/projects/{pid}").text
        assert "super-secret-123" not in proj and '"has_secret":true' in proj.replace(" ", "")
        assert "super-secret-123" not in store._db.execute("SELECT config FROM projects").fetchone()[0]
        assert "super-secret-123" not in client.get(f"/api/projects/{pid}/export.yaml").text


def test_api_rejects_foreign_hosts_header_and_bad_config():
    with TestClient(create_app(Store(":memory:"))) as client:
        assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400
        r = client.post("/api/projects", json={"name": "x", "target": {"base_url": "http://api.example.com"}})
        assert r.status_code == 422
