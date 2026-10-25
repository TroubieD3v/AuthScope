"""Shared building blocks for test modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..compare import Observation, classify
from ..config import Endpoint, Identity, ProjectConfig, Resource
from ..http_engine import RawResponse
from ..models import Severity

SEVERITY_BY_MODULE: dict[str, Severity] = {
    "bola": "high", "bfla": "high", "bopla": "medium", "unauth": "high",
    "tenant": "critical", "custom": "medium",
}


@dataclass
class Case:
    module: str
    name: str
    endpoint: Endpoint
    identity: Identity | None
    expected: str | None  # "allow" | "deny"
    mode: str = "identity"  # identity | none | invalid
    resource: Resource | None = None
    baseline_identity: Identity | None = None
    variant: str | None = None
    kind: str = "access"  # access | list_leak | fields
    reason: str = ""  # why this expectation (policy explanation)
    skip_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    identity_label: str | None = None  # shown name when identity is None / anonymous variant

    @property
    def identity_name(self) -> str | None:
        return self.identity.name if self.identity else self.identity_label


@dataclass
class Judgement:
    verdict: str
    observed: str
    message: str
    severity: Severity = "info"
    diff: list[str] = field(default_factory=list)


class Module(Protocol):
    name: str
    title: str
    description: str

    def plan(self, cfg: ProjectConfig) -> list[Case]: ...

    def evaluate(self, case: Case, test: RawResponse, baseline: RawResponse | None) -> Judgement: ...


def bump(sev: Severity, mutating: bool) -> Severity:
    if not mutating:
        return sev
    order = ["info", "low", "medium", "high", "critical"]
    return order[min(order.index(sev) + 1, 4)]  # type: ignore[return-value]


def observe(case: Case, test: RawResponse, baseline: RawResponse | None) -> Observation:
    res = case.resource
    obs = classify(test, baseline=baseline, id_field=res.id_field if res else "id",
                   resource_id=res.id if res else None)
    if case.endpoint.mutating and obs.kind in ("allowed_empty", "allowed_ambiguous"):
        obs = Observation("allowed_data", f"HTTP {test.status} - state-changing request accepted")
    return obs


def judge_access(case: Case, test: RawResponse, baseline: RawResponse | None) -> Judgement:
    """Core table: expected policy x observed behaviour -> verdict."""
    obs = observe(case, test, baseline)
    base_sev = bump(SEVERITY_BY_MODULE.get(case.module, "medium"), case.endpoint.mutating)
    k = obs.kind

    if k == "transport_error":
        return Judgement("error", k, obs.detail)
    if k in ("rejected", "server_error", "redirect"):
        return Judgement("inconclusive", k, f"{obs.detail}; authorization was not actually evaluated")

    if case.expected == "deny":
        if k == "allowed_data":
            return Judgement("violation", k, f"Access was expected to be denied but succeeded: {obs.detail}",
                             base_sev)
        if k == "allowed_ambiguous":
            return Judgement("needs_review", k,
                             f"{obs.detail}. The endpoint may ignore the object id and return the caller's "
                             "own data - verify manually", "medium")
        if k == "allowed_empty":
            return Judgement("pass", k, f"{obs.detail}: no data was exposed (not classified as a violation)")
        if k == "soft_denied":
            return Judgement("pass", k, f"{obs.detail}: denied via an error body")
        return Judgement("pass", k, f"Denied as expected ({obs.detail})")

    # expected == allow
    if k in ("allowed_data", "allowed_empty", "allowed_ambiguous"):
        return Judgement("pass", k, f"Allowed as expected ({obs.detail})")
    return Judgement("needs_review", k,
                     f"Access was expected to be allowed but was denied ({obs.detail}); "
                     "either the policy or the API behaviour is off", "low")


def anonymous_identity(cfg: ProjectConfig) -> Identity | None:
    return next((i for i in cfg.identities if i.anonymous), None)


def authenticated(cfg: ProjectConfig) -> list[Identity]:
    return [i for i in cfg.identities if not i.anonymous]


def first_resource(cfg: ProjectConfig, ep: Endpoint) -> Resource | None:
    return cfg.resources_of(ep.resource_type)[0] if ep.resource_type and cfg.resources_of(ep.resource_type) else None


def enabled_endpoints(cfg: ProjectConfig) -> list[Endpoint]:
    return [e for e in cfg.endpoints if e.enabled]


def mutating_skip(cfg: ProjectConfig, ep: Endpoint) -> str | None:
    if ep.mutating and not cfg.target.allow_mutating:
        return "state-changing method; enable mutating mode (with test data + reset) to run it"
    return None


def object_policy_endpoint(cfg: ProjectConfig, rtype: str) -> Endpoint | None:
    """The single-object GET endpoint that defines who may read objects of this type."""
    for e in enabled_endpoints(cfg):
        if e.method == "GET" and e.resource_type == rtype and e.bound_param:
            return e
    return None
