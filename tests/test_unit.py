import ipaddress

import pytest

from authscope.compare import classify, find_fields, is_error_envelope
from authscope.config import ProjectConfig, TargetConfig
from authscope.http_engine import RawResponse
from authscope.masking import Masker
from authscope.openapi_import import endpoints_from_openapi, parse_document
from authscope.policy import decide
from authscope.safety import SafetyError, TargetGuard, ip_is_forbidden


def resp(status=200, body="", headers=None):
    return RawResponse(method="GET", url="http://x/y", label="t", identity=None, request_headers={},
                       request_body=None, status=status, text=body, headers=headers or {})


OWNER = resp(200, '{"id": 101, "item": "keyboard", "total": 129.9, "address": "12 Birch"}')


# -- comparison ---------------------------------------------------------------------------
def test_status_denials():
    for s in (401, 403, 404):
        assert classify(resp(s)).kind == "denied"


@pytest.mark.parametrize("body", ["[]", "{}", "null", "", '{"items": [], "total": 0}'])
def test_empty_200_is_not_data(body):
    assert classify(resp(200, body), baseline=OWNER, resource_id="101").kind == "allowed_empty"


def test_error_envelope_in_200_is_soft_denial():
    assert classify(resp(200, '{"error": "forbidden"}'), baseline=OWNER, resource_id="101").kind == "soft_denied"
    assert is_error_envelope({"success": False, "message": "no"})
    assert not is_error_envelope({"id": 1, "status": "paid"})


def test_same_object_is_allowed_data():
    o = classify(resp(200, OWNER.text), baseline=OWNER, id_field="id", resource_id="101")
    assert o.kind == "allowed_data" and o.overlap == 1.0


def test_similar_data_without_the_object_id_is_not_a_violation():
    # a different order that happens to share item, total and address with the owner's order
    other = resp(200, '{"id": 102, "item": "keyboard", "total": 129.9, "address": "12 Birch"}')
    o = classify(other, baseline=OWNER, id_field="id", resource_id="101")
    assert o.kind == "allowed_ambiguous" and o.overlap == 0.75 and "not proven" in o.detail


def test_coincidental_id_with_unrelated_data_is_ambiguous():
    o = classify(resp(200, '{"id": 101, "kind": "coupon", "code": "X1"}'), baseline=OWNER, resource_id="101")
    assert o.kind == "allowed_ambiguous" and o.id_match and "coincidental" in o.detail


def test_id_match_without_baseline_is_enough():
    assert classify(resp(200, '{"id": 101, "x": 1}'), resource_id="101").kind == "allowed_data"


def test_function_level_similarity_without_resource():
    base = resp(200, '{"users": 4, "orders": 3}')
    assert classify(resp(200, '{"users": 4, "orders": 3}'), baseline=base).kind == "allowed_data"


def test_200_with_other_data_is_ambiguous_not_violation():
    o = classify(resp(200, '{"id": 7, "item": "sock", "total": 3}'), baseline=OWNER, resource_id="101")
    assert o.kind == "allowed_ambiguous"


def test_login_redirect_is_denial_other_redirect_is_not():
    assert classify(resp(302, headers={"location": "/login?next=/x"})).kind == "denied"
    assert classify(resp(302, headers={"location": "/elsewhere"})).kind == "redirect"


def test_rejected_and_server_errors_are_inconclusive_kinds():
    assert classify(resp(422)).kind == "rejected"
    assert classify(resp(500)).kind == "server_error"


def test_find_fields_is_case_style_insensitive():
    data = {"user": {"internal_notes": "x", "name": "a"}, "list": [{"InternalNotes": ""}]}
    assert find_fields(data, "internalNotes") == ["user.internal_notes"]  # empty value is not exposure
    assert find_fields({"profile": {"ssn": "1"}}, "profile.ssn") == ["profile.ssn"]


# -- masking ------------------------------------------------------------------------------
def test_masking_covers_headers_json_and_known_tokens():
    m = Masker({"alice": "demo-alice-0f3a9c71"})
    assert m.headers({"Authorization": "Bearer abc"})["Authorization"] == "***REDACTED***"
    body = m.body('{"password": "hunter2", "email": "alice@acme.test", "note": "tok demo-alice-0f3a9c71", '
                  '"card": "4111 1111 1111 1111"}')
    assert "hunter2" not in body and "alice@acme.test" not in body
    assert "demo-alice-0f3a9c71" not in body and "{{token:alice}}" in body
    assert "4111" not in body


def test_masking_truncates_long_bodies():
    assert "truncated" in Masker().body("x" * 5000)


# -- safety -------------------------------------------------------------------------------
def target(**kw):
    return TargetConfig(base_url="http://127.0.0.1:8000", **kw)


def test_non_loopback_requires_explicit_allowlist():
    with pytest.raises(ValueError):
        TargetConfig(base_url="http://api.example.com")
    assert TargetConfig(base_url="http://api.example.com", allowed_hosts=["api.example.com"])
    with pytest.raises(ValueError):
        TargetConfig(base_url="http://api.example.com", allowed_hosts=["*.example.com", "api.example.com"])


def test_mutating_needs_reset_or_ack():
    with pytest.raises(ValueError):
        target(allow_mutating=True)
    assert target(allow_mutating=True, acknowledge_no_reset=True)


def test_guard_blocks_foreign_hosts_ports_and_odd_paths():
    g = TargetGuard(target())
    g.check_url("http://127.0.0.1:8000/x")
    for bad in ("http://evil.test/", "http://127.0.0.1:9999/", "ftp://127.0.0.1:8000/", "http://u:p@127.0.0.1:8000/"):
        with pytest.raises(SafetyError):
            g.check_url(bad)
    for bad in ("//evil.test/x", "http://evil.test", "/a\\b"):
        with pytest.raises(SafetyError):
            g.build_url(bad)
    with pytest.raises(SafetyError):
        g.resolve_redirect("http://127.0.0.1:8000/a", "http://169.254.169.254/latest/meta-data")
    with pytest.raises(SafetyError):
        g.check_method("DELETE")


def test_metadata_and_link_local_addresses_are_forbidden():
    for ip in ("169.254.169.254", "fe80::1", "224.0.0.1", "0.0.0.0"):
        assert ip_is_forbidden(ipaddress.ip_address(ip))
    assert not ip_is_forbidden(ipaddress.ip_address("127.0.0.1"))


# -- policy -------------------------------------------------------------------------------
def cfg():
    return ProjectConfig.model_validate({
        "target": {"base_url": "http://127.0.0.1:8000"},
        "identities": [{"name": "alice", "tenant": "a"}, {"name": "bob", "tenant": "a"},
                       {"name": "admin", "role": "admin"}, {"name": "guest", "role": "guest"}],
        "resources": [{"type": "order", "id": 101, "owner": "alice"}],
        "endpoints": [{"method": "GET", "path": "/o/{order_id}", "access": "owner", "allow_roles": ["admin"],
                       "resource_type": "order"},
                      {"method": "GET", "path": "/admin", "access": "roles", "allow_roles": ["admin"]}],
        "overrides": [{"endpoint": "GET /o/{order_id}", "identity": "bob", "expected": "allow"}],
    })


def test_policy_owner_roles_override_and_anonymous():
    c = cfg()
    ep, adm = c.endpoints
    res = c.resources[0]
    assert decide(c, ep, c.identity("alice"), res).allow
    assert decide(c, ep, c.identity("admin"), res).allow
    assert decide(c, ep, c.identity("bob"), res).overridden
    c.overrides.clear()
    assert not decide(c, ep, c.identity("bob"), res).allow
    assert not decide(c, ep, c.identity("guest"), res).allow
    assert not decide(c, adm, c.identity("alice")).allow and decide(c, adm, c.identity("admin")).allow


def test_identity_defaults_token_env_and_guest():
    c = cfg()
    assert c.identity("alice").token_env == "AUTHSCOPE_TOKEN_ALICE"
    assert c.identity("guest").anonymous and c.identity("guest").token_env is None
    assert ProjectConfig.model_validate({"target": {"base_url": "http://localhost:1"},
                                         "identities": ["x", "y"]}).identities[1].name == "y"


# -- openapi import -----------------------------------------------------------------------
SPEC = """
openapi: 3.0.0
info: {title: t, version: '1'}
components: {securitySchemes: {b: {type: http, scheme: bearer}}}
security: [{b: []}]
paths:
  /health: {get: {security: [], summary: ping}}
  /orders: {get: {summary: list}}
  /orders/{order_id}:
    get: {summary: one}
    put:
      requestBody: {content: {application/json: {schema: {type: object, required: [status], properties: {status: {type: string}}}}}}
  /admin/stats: {get: {}}
"""


def test_openapi_import_infers_rules():
    eps = {e.key: e for e in endpoints_from_openapi(parse_document(SPEC))}
    assert eps["GET /health"].access == "public"
    assert eps["GET /orders"].list_of == "order"
    assert eps["GET /orders/{order_id}"].access == "owner" and eps["GET /orders/{order_id}"].resource_type == "order"
    assert eps["PUT /orders/{order_id}"].body == {"status": "string"}
    assert eps["GET /admin/stats"].access == "roles" and all(e.inferred for e in eps.values())


# -- postman import -----------------------------------------------------------------------
def test_postman_import_converts_paths_auth_and_bodies():
    from pathlib import Path

    from authscope.postman_import import endpoints_from_postman, is_postman, parse_collection

    text = (Path(__file__).resolve().parents[1] / "examples" / "demo.postman_collection.json").read_text(encoding="utf-8")
    doc = parse_collection(text)
    assert is_postman(doc)
    eps = {e.key: e for e in endpoints_from_postman(doc)}
    assert eps["GET /health"].access == "public"  # request-level noauth
    assert eps["GET /api/users/me"].access == "authenticated"
    assert eps["GET /api/users/{user_id}"].access == "owner" and eps["GET /api/users/{user_id}"].resource_type == "user"
    assert eps["PUT /api/users/{user_id}"].body == {"username": "new-name"}
    assert eps["GET /api/orders/{orderId}"].resource_type == "order"
    assert eps["GET /api/orders"].list_of == "order"
    assert eps["GET /api/admin/stats"].access == "roles" and eps["GET /api/admin/stats"].query == {"verbose": "1"}
    assert eps["GET /api/users/{user_id}"].tags == ["users"] and all(e.source == "postman" for e in eps.values())


def test_postman_parser_rejects_other_json():
    from authscope.openapi_import import ImportErrorInfo
    from authscope.postman_import import parse_collection

    with pytest.raises(ImportErrorInfo):
        parse_collection('{"openapi": "3.0.0", "paths": {}}')


# -- auth formats / nested paths ------------------------------------------------------------
def _ident(**auth):
    from authscope.config import Identity

    return Identity(name="alice", auth=auth)


def test_query_and_basic_auth_are_applied():
    import base64

    from authscope.http_engine import Requester

    r = Requester(TargetConfig(base_url="http://127.0.0.1:8000"), lambda i: "s3cret-value")
    assert r._auth(_ident(type="query", query_name="key"), "identity") == ({}, {}, {"key": "s3cret-value"})
    h, _, _ = r._auth(_ident(type="basic", username="alice"), "identity")
    assert base64.b64decode(h["Authorization"][6:]) == b"alice:s3cret-value"
    h, _, _ = r._auth(_ident(type="bearer"), "invalid")
    assert h["Authorization"] == "Bearer authscope-invalid-token"
    assert "alice:basic" in r.secret_values([_ident(type="basic", username="alice")])


def test_curl_uses_placeholders_for_query_and_basic():
    from authscope.evidence import curl_command

    raw = RawResponse(method="GET", url="http://h/x?page=2&key=s3cret-value", label="t", identity="alice",
                      request_headers={}, request_body=None)
    cmd = curl_command(raw, _ident(type="query", query_name="key"), "identity")
    assert "s3cret-value" not in cmd and "key=$AUTHSCOPE_TOKEN_ALICE" in cmd and "page=2" in cmd
    cmd = curl_command(raw, _ident(type="basic", username="alice"), "identity")
    assert '-u "alice:$AUTHSCOPE_TOKEN_ALICE"' in cmd


def test_nested_path_values_use_parent_then_owner():
    c = ProjectConfig.model_validate({
        "target": {"base_url": "http://127.0.0.1:8000"},
        "identities": ["alice"],
        "resources": [{"type": "user", "id": 1, "owner": "alice"}, {"type": "shop", "id": 7, "owner": "alice"},
                      {"type": "order", "id": 101, "owner": "alice", "parent": "user:1"}],
        "endpoints": [{"method": "GET", "path": "/users/{user_id}/shops/{shop_id}/orders/{order_id}",
                       "access": "owner", "resource_type": "order"}],
    })
    ep = c.endpoints[0]
    assert ep.bound_param == "order_id"
    assert c.path_values(ep, c.resource("order:101")) == {"order_id": "101", "user_id": "1", "shop_id": "7"}


def test_openapi_nested_paths_get_param_types():
    from authscope.openapi_import import infer_rules

    r = infer_rules("get", "/users/{user_id}/orders/{order_id}", False)
    assert r["resource_type"] == "order" and r["param_types"] == {"user_id": "user", "order_id": "order"}
    assert r["access"] == "owner"


# -- DNS pinning ----------------------------------------------------------------------------
async def test_pin_connects_to_the_validated_ip_and_keeps_the_name():
    g = TargetGuard(TargetConfig(base_url="https://api.example.test", allowed_hosts=["api.example.test"]))

    async def fake_resolve(url):
        return [ipaddress.ip_address("203.0.113.7")]

    g.check_resolved = fake_resolve  # type: ignore[method-assign]
    p = await g.pin("https://api.example.test/orders/1?x=1")
    assert p.url == "https://203.0.113.7:443/orders/1?x=1"
    assert p.host == "api.example.test" and p.sni == "api.example.test" and p.extensions == {"sni_hostname": "api.example.test"}


async def test_requester_resolves_once_and_never_reconnects_by_name(monkeypatch):
    import httpx

    from authscope.http_engine import Requester

    target = TargetConfig(base_url="http://api.example.test:8000", allowed_hosts=["api.example.test"])
    req = Requester(target, lambda i: None)
    answers = iter([[ipaddress.ip_address("198.51.100.10")], [ipaddress.ip_address("169.254.169.254")]])
    calls = []

    async def rebinding_dns(url):
        calls.append(url)
        return next(answers)  # a second lookup would return the metadata address

    req.guard.check_resolved = rebinding_dns  # type: ignore[method-assign]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers["host"], request.headers.get("cookie")))
        return httpx.Response(200, json={"ok": True})

    await req._client.aclose()
    req._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    from authscope.config import Identity

    raw = await req.send("GET", "/a", identity=Identity(name="c", auth={"type": "cookie", "cookie_name": "sid"}))
    await req.aclose()
    assert raw.status == 200 and len(calls) == 1
    assert seen == [("http://198.51.100.10:8000/a", "api.example.test:8000", None)]  # no token -> no cookie
    assert raw.url == "http://api.example.test:8000/a"  # evidence shows the name, not the IP


async def test_pin_refuses_forbidden_answers():
    g = TargetGuard(TargetConfig(base_url="http://api.example.test", allowed_hosts=["api.example.test"]))

    async def metadata_dns(url):
        from authscope.safety import ip_is_forbidden

        ip = ipaddress.ip_address("169.254.169.254")
        if ip_is_forbidden(ip):
            raise SafetyError("forbidden")
        return [ip]

    g.check_resolved = metadata_dns  # type: ignore[method-assign]
    with pytest.raises(SafetyError):
        await g.pin("http://api.example.test/x")
