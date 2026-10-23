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
