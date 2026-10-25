"""JSONPath subset and composite identifiers."""
import pytest

from authscope.compare import classify
from authscope.config import Endpoint, ProjectConfig, Resource
from authscope.http_engine import RawResponse
from authscope.jsonpath import JsonPathError, last_key, matches, values
from authscope.modules.base import Case, judge_access

DOC = {"data": {"order": {"tenant": "acme", "number": 101, "lines": [{"sku": "KB-77"}, {"sku": "MS-1"}]}},
       "meta": {"tenant": "acme"}}


def resp(body: str, status: int = 200) -> RawResponse:
    return RawResponse(method="GET", url="http://x/y", label="t", identity=None, request_headers={},
                       request_body=None, status=status, text=body)


def test_jsonpath_subset():
    assert values(DOC, "$.data.order.number") == [101]
    assert values(DOC, "$['data']['order']['tenant']") == ["acme"]
    assert values(DOC, "$.data.order.lines[1].sku") == ["MS-1"]
    assert values(DOC, "$.data.order.lines[*].sku") == ["KB-77", "MS-1"]
    assert sorted(values(DOC, "$..tenant")) == ["acme", "acme"]
    assert values(DOC, "$.missing.key") == []
    assert last_key("$.data.order.number") == "number"
    with pytest.raises(JsonPathError):
        values(DOC, "data.order")
    with pytest.raises(JsonPathError):
        values(DOC, "$.lines[?(@.sku)]")


def test_composite_rules_need_every_part():
    assert matches(DOC, {"$.data.order.tenant": "acme", "$.data.order.number": "101"})
    assert not matches(DOC, {"$.data.order.tenant": "globex", "$.data.order.number": "101"})
    assert not matches(DOC, {})


OWNER = resp('{"tenant": "acme", "number": 101, "item": "keyboard", "total": 129.9}')
RULES = {"$.tenant": "acme", "$.number": "101"}


def test_composite_identifier_violation_and_lookalikes():
    same = classify(resp(OWNER.text), baseline=OWNER, resource_id="acme/101", match=RULES)
    assert same.kind == "allowed_data" and "match rules" in same.detail
    # same order number, other tenant: a different object -> never a confirmed violation
    other_tenant = classify(resp('{"tenant": "globex", "number": 101, "item": "keyboard", "total": 129.9}'),
                            baseline=OWNER, resource_id="acme/101", match=RULES)
    assert other_tenant.kind == "allowed_ambiguous"


def test_match_rules_find_objects_inside_lists():
    body = '{"items": [{"tenant": "globex", "number": 7}, {"tenant": "acme", "number": 101, "item": "keyboard"}]}'
    assert classify(resp(body), resource_id="acme/101", match=RULES).kind == "allowed_data"


def test_ambiguous_stays_needs_review_never_high():
    res = Resource(type="order", id="acme/101", owner="alice", match=RULES)
    case = Case(module="bola", name="t", endpoint=Endpoint(method="GET", path="/o/{id}"), identity=None,
                expected="deny", resource=res)
    j = judge_access(case, resp('{"tenant": "globex", "number": 101, "item": "keyboard", "total": 129.9}'), OWNER)
    assert j.verdict == "needs_review" and j.severity not in ("high", "critical")


def test_config_validates_rules():
    base = {"target": {"base_url": "http://127.0.0.1:1"}}
    cfg = ProjectConfig.model_validate({**base, "resources": [{"type": "o", "id": "a/1", "match": {"$.n": 1}}]})
    assert cfg.resources[0].match == {"$.n": "1"}
    with pytest.raises(ValueError):
        ProjectConfig.model_validate({**base, "resources": [{"type": "o", "id": "x", "match": {"n": 1}}]})
