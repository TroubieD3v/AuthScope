"""BOPLA: does a response expose properties the caller's role may not see (e.g. internalNotes)?"""
from __future__ import annotations

from ..compare import classify, find_fields
from ..config import ProjectConfig, RestrictedField
from ..models import Severity
from ..policy import decide
from .base import Case, Judgement, bump, enabled_endpoints, mutating_skip

_SEVERITY: Severity = "medium"


def _split(cfg: ProjectConfig, ident, res, fields: list[RestrictedField]):
    restricted, entitled = [], []
    for f in fields:
        owner_ok = f.owner_can_see and res is not None and res.owner == ident.name
        (entitled if ident.role in f.roles or owner_ok else restricted).append(f.name)
    return restricted, entitled


class BoplaModule:
    name = "bopla"
    title = "BOPLA"
    description = ("Reads objects as every identity allowed to see them and fails if a restricted JSON "
                   "property shows up for a role that must not see it. Entitled roles act as controls.")

    def plan(self, cfg: ProjectConfig) -> list[Case]:
        cases: list[Case] = []
        for ep in enabled_endpoints(cfg):
            if not ep.restricted_fields:
                continue
            resources = cfg.resources_of(ep.resource_type) if ep.bound_param and ep.resource_type else [None]
            for res in resources:
                for ident in cfg.identities:
                    d = decide(cfg, ep, ident, res)
                    if not d.allow:
                        continue  # access itself is covered by BOLA / BFLA / unauth
                    restricted, entitled = _split(cfg, ident, res, ep.restricted_fields)
                    target = f"[{res.ref}]" if res else ""
                    cases.append(Case(
                        module=self.name, endpoint=ep, identity=ident, resource=res, expected="allow",
                        kind="fields", reason=d.reason,
                        name=f"{ident.name} ({ident.role}) reads {ep.key}{target}: "
                             f"{', '.join(restricted) or 'control'}",
                        variant="fields", skip_reason=mutating_skip(cfg, ep),
                        extra={"restricted": restricted, "entitled": entitled},
                    ))
        return cases

    def evaluate(self, case: Case, test, baseline) -> Judgement:
        obs = classify(test, id_field=case.resource.id_field if case.resource else "id",
                       resource_id=case.resource.id if case.resource else None)
        if obs.kind == "transport_error":
            return Judgement("error", obs.kind, obs.detail)
        if not obs.allowed or test.json is None:
            return Judgement("inconclusive", obs.kind,
                             f"Could not inspect the response ({obs.detail}); expected an allowed JSON response")
        restricted: list[str] = case.extra["restricted"]
        entitled: list[str] = case.extra["entitled"]

        exposed = {f: paths for f in restricted if (paths := find_fields(test.json, f))}
        if exposed:
            detail = "; ".join(f"'{f}' at {', '.join(p[:3])}" for f, p in exposed.items())
            return Judgement("violation", obs.kind,
                             f"Role '{case.identity.role if case.identity else '?'}' received restricted "
                             f"propert{'y' if len(exposed) == 1 else 'ies'}: {detail}",
                             bump(_SEVERITY, False),
                             diff=[f"Restricted fields present: {', '.join(exposed)}"])
        if restricted:
            return Judgement("pass", obs.kind,
                             f"None of the restricted fields were returned: {', '.join(restricted)}")
        seen = [f for f in entitled if find_fields(test.json, f)]
        if len(seen) == len(entitled):
            return Judgement("pass", obs.kind, f"Control: entitled role sees {', '.join(entitled)}")
        missing = [f for f in entitled if f not in seen]
        return Judgement("inconclusive", obs.kind,
                         f"Control: entitled role does not see {', '.join(missing)}; the field name may be "
                         "wrong, so a clean result for other roles proves nothing")
