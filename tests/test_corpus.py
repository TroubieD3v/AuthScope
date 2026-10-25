"""#5: annotated false-positive corpus and property-based tests for comparison and masking."""
import json
import string
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from authscope.compare import classify
from authscope.http_engine import RawResponse
from authscope.masking import Masker

CORPUS = yaml.safe_load((Path(__file__).parent / "corpus" / "cases.yaml").read_text(encoding="utf-8"))["cases"]


def raw(status, body="", headers=None) -> RawResponse:
    return RawResponse(method="GET", url="http://x/y", label="t", identity=None, request_headers={},
                       request_body=None, status=status, text=body, headers=headers or {})


def test_corpus_is_large_enough_and_names_are_unique():
    names = [c["name"] for c in CORPUS]
    assert len(names) >= 30 and len(names) == len(set(names))


@pytest.mark.parametrize("case", CORPUS, ids=[c["name"] for c in CORPUS])
def test_corpus_case(case):
    baseline = raw(200, case["baseline"]) if case.get("baseline") else None
    obs = classify(raw(case["status"], case.get("body", ""), case.get("headers")), baseline=baseline,
                   id_field=case.get("id_field", "id"), resource_id=case.get("resource_id"), match=case.get("match"))
    assert obs.kind == case["expected"], obs.detail


# -- property-based ----------------------------------------------------------------------------------
scalars = st.one_of(st.none(), st.booleans(), st.integers(-10**6, 10**6), st.floats(allow_nan=False, allow_infinity=False),
                    st.text(max_size=12))
json_docs = st.recursive(scalars, lambda inner: st.one_of(
    st.lists(inner, max_size=4), st.dictionaries(st.text(string.ascii_letters, min_size=1, max_size=8), inner, max_size=4)),
    max_leaves=20)


def _contains_id(doc, wanted="101"):
    if isinstance(doc, dict):
        return any((k == "id" and not isinstance(v, (dict, list)) and str(v) == wanted) or _contains_id(v, wanted)
                   for k, v in doc.items())
    if isinstance(doc, list):
        return any(_contains_id(v, wanted) for v in doc)
    return False


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(doc=json_docs)
def test_no_object_level_confirmation_without_the_object_id(doc):
    """Whatever the body looks like, a 200 without the requested id is never a confirmed violation."""
    owner = raw(200, json.dumps({"id": 101, "item": "keyboard", "total": 129.9, "status": "paid"}))
    obs = classify(raw(200, json.dumps(doc)), baseline=owner, resource_id="101")
    if not _contains_id(doc):
        assert obs.kind != "allowed_data"


@settings(max_examples=300)
@given(status=st.integers(100, 599), body=st.text(max_size=200))
def test_classify_never_crashes(status, body):
    classify(raw(status, body), resource_id="1")
    classify(raw(status, body))


secrets = st.text(string.ascii_letters + string.digits + "-_.", min_size=8, max_size=40)


@settings(max_examples=200)
@given(secret=secrets, key=st.text(string.ascii_letters, min_size=1, max_size=10),
       depth=st.integers(0, 3), noise=st.text(max_size=20))
def test_known_secret_never_survives_masking(secret, key, depth, noise):
    m = Masker({"alice": secret})
    doc: object = f"{noise}{secret}{noise}"
    for _ in range(depth):
        doc = {key: [doc]}
    body = m.body(json.dumps({"payload": doc}), limit=100_000)
    assert secret not in (body or "")
    assert secret not in m.text(f"http://h/x?{key}={secret}&a=1")
    assert secret not in "".join(m.headers({"X-Custom": f"t {secret}", key: secret}).values())
