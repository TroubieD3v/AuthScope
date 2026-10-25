"""Object-level access testing shared by BOLA (same tenant) and Cross-Tenant (different tenants)."""
from __future__ import annotations

from ..compare import classify, collect_ids
from ..config import Identity, ProjectConfig, Resource
from ..http_engine import RawResponse
from ..policy import Decision, decide
from .base import (Case, Judgement, SEVERITY_BY_MODULE, authenticated, bump, enabled_endpoints,
                   judge_access, mutating_skip, object_policy_endpoint)


def _differs(cfg: ProjectConfig, ident: Identity, res: Resource) -> bool:
    tenant = cfg.tenant_of(res)
    return bool(ident.tenant and tenant and ident.tenant != tenant)


def _expected(cfg: ProjectConfig, module: str, ep, ident: Identity, res: Resource) -> Decision:
    d = decide(cfg, ep, ident, res)
    if module == "tenant" and not d.overridden and _differs(cfg, ident, res):
        return Decision(False, f"tenant '{ident.tenant}' must not reach tenant '{cfg.tenant_of(res)}'")
    return d


def plan_object_cases(cfg: ProjectConfig, module: str) -> list[Case]:
    cross = module == "tenant"
    cases: list[Case] = []
    for ep in enabled_endpoints(cfg):
        # -- direct object access --------------------------------------------------------
        if ep.bound_param and ep.resource_type and ep.access in ("owner", "tenant", "authenticated"):
            for res in cfg.resources_of(ep.resource_type):
                owner = cfg.identity(res.owner) if res.owner else None
                for ident in authenticated(cfg):
                    if _differs(cfg, ident, res) != cross:
                        continue
                    d = _expected(cfg, module, ep, ident, res)
                    case = Case(
                        module=module, endpoint=ep, identity=ident, resource=res,
                        expected="allow" if d.allow else "deny", reason=d.reason,
                        name=f"{ident.name} -> {ep.key} [{res.ref}]",
                        baseline_identity=owner if owner and not ep.mutating else None,
                        skip_reason=mutating_skip(cfg, ep),
                    )
                    cases.append(case)
        # -- list endpoints must not leak other users' objects ----------------------------
        elif ep.list_of and ep.method == "GET":
            detail = object_policy_endpoint(cfg, ep.list_of)
            for ident in authenticated(cfg):
                foreign = []
                for res in cfg.resources_of(ep.list_of):
                    if _differs(cfg, ident, res) != cross:
                        continue
                    if not _expected(cfg, module, detail or ep, ident, res).allow:
                        foreign.append(res)
                if not foreign:
                    continue
                cases.append(Case(
                    module=module, endpoint=ep, identity=ident, expected="deny", kind="list_leak",
                    name=f"{ident.name} -> {ep.key} must not list {len(foreign)} foreign {ep.list_of}(s)",
                    reason="list must only contain objects the caller may access",
                    variant="list_leak", extra={"foreign": [r.ref for r in foreign],
                                                "id_field": foreign[0].id_field},
                    skip_reason=None,
                ))
    return cases


def evaluate_object_case(case: Case, test: RawResponse, baseline: RawResponse | None) -> Judgement:
    if case.kind != "list_leak":
        return judge_access(case, test, baseline)

    obs = classify(test)
    sev = bump(SEVERITY_BY_MODULE[case.module], False)
    if obs.kind == "transport_error":
        return Judgement("error", obs.kind, obs.detail)
    if not obs.allowed:
        return Judgement("pass", obs.kind, f"List not served to this identity ({obs.detail})")
    foreign_ids = {r.split(":", 1)[1] for r in case.extra["foreign"]}
    ids = collect_ids(test.json, case.extra["id_field"])
    leaked = sorted(ids & foreign_ids)
    if leaked:
        return Judgement("violation", obs.kind,
                         f"List response exposes {len(leaked)} object(s) this identity must not see: "
                         + ", ".join(leaked), sev,
                         diff=[f"Returned ids: {', '.join(sorted(ids)) or '-'}",
                               f"Foreign ids present: {', '.join(leaked)}"])
    return Judgement("pass", obs.kind,
                     f"List returned {len(ids)} object id(s); none of the {len(foreign_ids)} foreign objects")
