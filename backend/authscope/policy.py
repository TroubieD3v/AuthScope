"""Expected-access policy: derives allow/deny for (endpoint, identity, resource)."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Endpoint, Identity, ProjectConfig, Resource


@dataclass
class Decision:
    allow: bool
    reason: str
    overridden: bool = False


def decide(cfg: ProjectConfig, ep: Endpoint, ident: Identity, res: Resource | None = None) -> Decision:
    for ov in cfg.overrides:
        if ov.endpoint != ep.key or ov.identity != ident.name:
            continue
        if ov.resource is None or (res is not None and ov.resource == res.ref):
            return Decision(ov.expected == "allow", "manual override", True)

    if ep.access == "public":
        return Decision(True, "endpoint is public")
    if ident.anonymous:
        return Decision(False, "anonymous identity on a protected endpoint")
    if ep.access == "authenticated":
        return Decision(True, "any authenticated identity")
    if ident.role in ep.allow_roles:
        return Decision(True, f"role '{ident.role}' is allowed")
    if ep.access == "roles":
        return Decision(False, f"requires role in {ep.allow_roles or ['?']}")
    if res is None:
        return Decision(True, "no concrete object - per-object rule cannot be evaluated")
    if ep.access == "owner":
        if res.owner == ident.name:
            return Decision(True, "identity owns the object")
        return Decision(False, f"object is owned by '{res.owner}'")
    if ep.access == "tenant":
        tenant = cfg.tenant_of(res)
        if ident.tenant and tenant and ident.tenant == tenant:
            return Decision(True, "same tenant")
        return Decision(False, f"object belongs to tenant '{tenant}'")
    return Decision(False, "unknown access rule")


def matrix_cell(cfg: ProjectConfig, ep: Endpoint, ident: Identity) -> str:
    """Summary of the expectation for the matrix UI: allow | deny | conditional."""
    if ep.resource_type and ep.access in ("owner", "tenant"):
        resources = cfg.resources_of(ep.resource_type)
        decisions = {decide(cfg, ep, ident, r).allow for r in resources}
        if decisions == {True}:
            return "allow"
        if decisions == {False}:
            return "deny"
        if decisions:
            return "conditional"
    return "allow" if decide(cfg, ep, ident).allow else "deny"
