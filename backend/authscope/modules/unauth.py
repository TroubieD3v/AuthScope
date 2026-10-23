"""Unauthenticated access: protected endpoints must refuse requests without a valid credential."""
from __future__ import annotations

from ..config import ProjectConfig
from .base import Case, Judgement, anonymous_identity, enabled_endpoints, first_resource, judge_access, mutating_skip


class UnauthModule:
    name = "unauth"
    title = "Unauthenticated Access"
    description = ("Calls every non-public endpoint with no credentials and with an invalid token; "
                   "public endpoints are checked as positive controls.")

    def plan(self, cfg: ProjectConfig) -> list[Case]:
        anon = anonymous_identity(cfg)
        label = anon.name if anon else "anonymous"
        cases: list[Case] = []
        for ep in enabled_endpoints(cfg):
            res = first_resource(cfg, ep) if ep.bound_param else None
            missing = None
            if ep.bound_param and res is None:
                missing = f"no test resource of type '{ep.resource_type}' configured for {{{ep.bound_param}}}"
            skip = missing or mutating_skip(cfg, ep)
            if ep.access == "public":
                if ep.method == "GET":
                    cases.append(Case(module=self.name, endpoint=ep, identity=anon, mode="none",
                                      identity_label=label, resource=res, expected="allow",
                                      reason="endpoint is public", variant="no_credentials",
                                      name=f"{ep.key} reachable without credentials (control)", skip_reason=skip))
                continue
            for mode, variant, text in (("none", "no_credentials", "no credentials"),
                                        ("invalid", "invalid_token", "invalid token")):
                cases.append(Case(module=self.name, endpoint=ep, identity=anon, mode=mode,
                                  identity_label=label, resource=res, expected="deny",
                                  reason="endpoint requires authentication", variant=variant,
                                  name=f"{ep.key} with {text}", skip_reason=skip))
        return cases

    def evaluate(self, case, test, baseline) -> Judgement:
        j = judge_access(case, test, baseline)
        if j.verdict == "violation":
            j.message = "Protected endpoint answered an unauthenticated request. " + j.message
        return j
