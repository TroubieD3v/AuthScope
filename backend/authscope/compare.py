"""Response comparison: classify what a response *means* instead of just reading the status code."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from . import jsonpath
from .http_engine import RawResponse
from .models import Observed

DENIED_STATUS = {401, 403, 404}
REJECTED_STATUS = {400, 405, 406, 409, 410, 415, 422}
ERROR_STATUS_WORDS = {"error", "fail", "failed", "forbidden", "unauthorized", "denied", "unauthenticated"}
LOGIN_HINTS = ("login", "signin", "sign-in", "auth", "sso")
SIMILAR_OVERLAP = 0.5  # share of the baseline's informative fields that makes two responses "similar"
MIN_CORROBORATION = 0.25  # an id match must also share this much of the owner's other fields


@dataclass
class Observation:
    kind: Observed
    detail: str
    overlap: float | None = None
    id_match: bool = False
    shared: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.kind in ("allowed_data", "allowed_empty", "allowed_ambiguous")


# -- JSON helpers -----------------------------------------------------------------------
def leaves(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (path, scalar) for every informative leaf. List indexes are generalised to []."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for v in value:
            yield from leaves(v, f"{path}[]")
    else:
        yield path, value


def informative(v: Any) -> bool:
    return not (v is None or v is False or v == 0 or (isinstance(v, str) and not v.strip()))


PAGINATION_KEYS = {"total", "count", "page", "pages", "page_size", "pagesize", "per_page", "perpage", "limit",
                   "offset", "next", "previous", "prev", "cursor", "has_more", "hasmore", "total_count", "totalcount"}
LOGIN_PAGE = re.compile(r"<form[^>]*>.*?(type=[\"']?password|name=[\"']?password)", re.I | re.S)


def is_empty_payload(data: Any, text: str) -> bool:
    if data is None:
        return not text.strip() or text.strip() == "null"
    if isinstance(data, dict) and any(isinstance(v, list) for v in data.values()):
        # a pagination wrapper with only empty lists is empty, whatever its counters say
        lists_empty = all(not v for v in data.values() if isinstance(v, list))
        others = {k for k, v in data.items() if not isinstance(v, list)}
        if lists_empty and all(_norm(k) in PAGINATION_KEYS or not informative(data[k]) for k in others):
            return True
    return not any(informative(v) for _, v in leaves(data))


def is_login_page(data: Any, text: str) -> bool:
    return data is None and bool(LOGIN_PAGE.search(text[:20000]))


def is_error_envelope(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("success") is False or data.get("ok") is False:
        return True
    status = data.get("status")
    if isinstance(status, str) and status.lower() in ERROR_STATUS_WORDS:
        return True
    for k in ("code", "statusCode", "status_code", "status"):
        if isinstance(data.get(k), int) and not isinstance(data.get(k), bool) and data[k] >= 400:
            return True
    for k in ("error", "errors", "detail"):
        if data.get(k) and len(data) <= 4:
            return True
    return False


def find_id(data: Any, id_field: str, wanted: str) -> bool:
    if isinstance(data, dict):
        for k, v in data.items():
            if k == id_field and not isinstance(v, (dict, list)) and str(v) == str(wanted):
                return True
            if find_id(v, id_field, wanted):
                return True
    elif isinstance(data, list):
        return any(find_id(v, id_field, wanted) for v in data)
    return False


def collect_ids(data: Any, id_field: str) -> set[str]:
    out: set[str] = set()
    if isinstance(data, dict):
        for k, v in data.items():
            if k == id_field and not isinstance(v, (dict, list)):
                out.add(str(v))
            else:
                out |= collect_ids(v, id_field)
    elif isinstance(data, list):
        for v in data:
            out |= collect_ids(v, id_field)
    return out


def _norm(name: str) -> str:
    return re.sub(r"[_\-\s]", "", name).lower()


def find_fields(data: Any, name: str) -> list[str]:
    """Paths where a field with this name (snake/camel-insensitive; dotted = path suffix) occurs."""
    target = [_norm(p) for p in name.split(".")]
    found: list[str] = []

    def walk(v: Any, trail: list[str]) -> None:
        if isinstance(v, dict):
            for k, child in v.items():
                nt = trail + [_norm(k)]
                if nt[-len(target):] == target and child not in (None, "", [], {}):
                    found.append(".".join(trail + [k]))
                walk(child, nt)
        elif isinstance(v, list):
            for child in v:
                walk(child, trail)

    walk(data, [])
    return found


# -- classification -----------------------------------------------------------------------
def identifies(data: Any, *, id_field: str, resource_id: str | None, match: dict[str, str] | None) -> bool:
    """Does the document contain the requested object? Match rules win over the plain id field."""
    if data is None or not resource_id:
        return False
    if match:
        return jsonpath.matches(data, match) or jsonpath.any_node_matches(data, match)
    return find_id(data, id_field, resource_id)


def classify(resp: RawResponse, *, baseline: RawResponse | None = None, id_field: str = "id",
             resource_id: str | None = None, match: dict[str, str] | None = None) -> Observation:
    if resp.error:
        return Observation("transport_error", resp.error)
    s = resp.status or 0
    if s in DENIED_STATUS:
        return Observation("denied", f"HTTP {s}")
    if 300 <= s < 400:
        loc = resp.headers.get("location", "")
        if any(h in loc.lower() for h in LOGIN_HINTS):
            return Observation("denied", f"HTTP {s} redirect to login ({loc})")
        return Observation("redirect", f"HTTP {s} redirect to {loc or '?'} (not followed)")
    if s == 429:
        return Observation("rate_limited", "HTTP 429 - rate limited even after retries")
    if s in REJECTED_STATUS or 400 <= s < 500:
        return Observation("rejected", f"HTTP {s} - request rejected before an authorization decision")
    if s >= 500 or s < 200:
        return Observation("server_error", f"HTTP {s}")

    data = resp.json
    if is_empty_payload(data, resp.text):
        return Observation("allowed_empty", f"HTTP {s} with empty payload")
    if is_login_page(data, resp.text):
        return Observation("soft_denied", f"HTTP {s} with a login form instead of data")
    id_match = identifies(data, id_field=id_field, resource_id=resource_id, match=match)
    if is_error_envelope(data) and not id_match:
        return Observation("soft_denied", f"HTTP {s} but body is an error envelope")

    overlap, shared, corroboration = None, [], None
    if baseline is not None and baseline.json is not None and data is not None:
        base_leaves = {(p, repr(v)) for p, v in leaves(baseline.json) if informative(v)}
        test_leaves = {(p, repr(v)) for p, v in leaves(data) if informative(v)}
        if base_leaves:
            common = base_leaves & test_leaves
            overlap = len(common) / len(base_leaves)
            shared = sorted(p for p, _ in common)
            # corroboration ignores the id itself: an id match must be backed by other identical fields
            id_keys = {id_field} | {k for k in (jsonpath.last_key(e) for e in (match or {})) if k}
            # compared by (field name, value) so the same object in a different wrapper still corroborates
            def keyed(items):
                return {(path.split(".")[-1].replace("[]", ""), value) for path, value in items}
            base_kv, test_kv = keyed(base_leaves), keyed(test_leaves)
            not_id = {x for x in base_kv if x[0] not in id_keys}
            corroboration = len(not_id & test_kv) / len(not_id) if not_id else None
    if resource_id is None:
        # function-level checks: there is no object to identify, data itself is the access
        if overlap is not None and overlap >= SIMILAR_OVERLAP:
            return Observation("allowed_data", f"HTTP {s}; {overlap:.0%} of the baseline's fields are identical",
                               overlap, False, shared)
        return Observation("allowed_data", f"HTTP {s} with data", overlap, False, shared)

    # Object-level checks: a violation needs the requested object's id in the response, corroborated by the
    # owner's baseline when there is one. Similar-looking data alone is never proof - two different orders
    # can share status, item and total - so it goes to manual review instead.
    if id_match and (corroboration is None or corroboration >= MIN_CORROBORATION):
        extra = f" and {overlap:.0%} of the owner's fields" if overlap is not None else ""
        what = "all match rules of " + resource_id if match else "object id " + resource_id
        return Observation("allowed_data", f"HTTP {s}; response contains {what}{extra}",
                           overlap, True, shared)
    if id_match:
        return Observation("allowed_ambiguous",
                           f"HTTP {s}; object id {resource_id} appears, but only {corroboration:.0%} of the "
                           "owner's other fields match - possibly a coincidental id", overlap, True, shared)
    if overlap is not None and overlap >= SIMILAR_OVERLAP:
        return Observation("allowed_ambiguous",
                           f"HTTP {s}; {overlap:.0%} of the owner's fields are identical, but object id "
                           f"{resource_id} was not found - similar data, not proven to be the same object",
                           overlap, False, shared)
    return Observation("allowed_ambiguous",
                       f"HTTP {s} with data, but it does not match the requested object", overlap, False, shared)


def diff_summary(baseline: RawResponse | None, test: RawResponse, obs: Observation) -> list[str]:
    lines: list[str] = []
    if baseline is not None:
        lines.append(f"Status: baseline {baseline.status} -> test {test.status}")
        lines.append(f"Body size: baseline {len(baseline.text)} B -> test {len(test.text)} B")
        if obs.overlap is not None:
            lines.append(f"Field overlap with baseline: {obs.overlap:.0%}")
        if obs.shared:
            shown = ", ".join(obs.shared[:8]) + (" ..." if len(obs.shared) > 8 else "")
            lines.append(f"Identical fields: {shown}")
        if baseline.json is not None and test.json is not None:
            bk = {p for p, _ in leaves(baseline.json)}
            tk = {p for p, _ in leaves(test.json)}
            if bk - tk:
                lines.append("Only in baseline: " + ", ".join(sorted(bk - tk)[:8]))
            if tk - bk:
                lines.append("Only in test: " + ", ".join(sorted(tk - bk)[:8]))
    else:
        lines.append(f"Status: {test.status}")
    lines.append(f"Classification: {obs.kind} ({obs.detail})")
    return lines
