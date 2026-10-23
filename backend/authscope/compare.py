"""Response comparison: classify what a response *means* instead of just reading the status code."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

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


def is_empty_payload(data: Any, text: str) -> bool:
    if data is None:
        return not text.strip() or text.strip() == "null"
    return not any(informative(v) for _, v in leaves(data))


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
def classify(resp: RawResponse, *, baseline: RawResponse | None = None, id_field: str = "id",
             resource_id: str | None = None) -> Observation:
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
    if s in REJECTED_STATUS:
        return Observation("rejected", f"HTTP {s} - request rejected before an authorization decision")
    if s >= 500 or s < 200:
        return Observation("server_error", f"HTTP {s}")

    data = resp.json
    if is_empty_payload(data, resp.text):
        return Observation("allowed_empty", f"HTTP {s} with empty payload")
    if is_error_envelope(data) and not (resource_id and find_id(data, id_field, resource_id)):
        return Observation("soft_denied", f"HTTP {s} but body is an error envelope")

    id_match = bool(resource_id) and data is not None and find_id(data, id_field, resource_id)
    overlap, shared, corroboration = None, [], None
    if baseline is not None and baseline.json is not None and data is not None:
        base_leaves = {(p, repr(v)) for p, v in leaves(baseline.json) if informative(v)}
        test_leaves = {(p, repr(v)) for p, v in leaves(data) if informative(v)}
        if base_leaves:
            common = base_leaves & test_leaves
            overlap = len(common) / len(base_leaves)
            shared = sorted(p for p, _ in common)
            # corroboration ignores the id itself: an id match must be backed by other identical fields
            not_id = {x for x in base_leaves if x[0].split(".")[-1].rstrip("[]") != id_field}
            corroboration = len(not_id & test_leaves) / len(not_id) if not_id else None
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
        return Observation("allowed_data", f"HTTP {s}; response contains object id {resource_id}{extra}",
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
