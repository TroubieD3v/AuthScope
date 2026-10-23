"""BFLA: can a role call functions that are reserved for other roles (e.g. admin)?"""
from __future__ import annotations

from ..config import ProjectConfig
from ..policy import decide
from .base import (Case, Judgement, authenticated, enabled_endpoints, first_resource, judge_access,
                   mutating_skip)


class BflaModule:
    name = "bfla"
    title = "BFLA"
    description = "Every authenticated role calls every role-restricted function; only allowed roles may succeed."

    def plan(self, cfg: ProjectConfig) -> list[Case]:
        cases: list[Case] = []
        for ep in enabled_endpoints(cfg):
            if ep.access != "roles":
                continue
            res = first_resource(cfg, ep) if ep.bound_param else None
            missing = None
            if ep.bound_param and res is None:
                missing = f"no test resource of type '{ep.resource_type}' configured for {{{ep.bound_param}}}"
            for ident in authenticated(cfg):
                d = decide(cfg, ep, ident, res)
                cases.append(Case(
                    module=self.name, endpoint=ep, identity=ident, resource=res,
                    expected="allow" if d.allow else "deny", reason=d.reason,
                    name=f"{ident.name} ({ident.role}) -> {ep.key}",
                    skip_reason=missing or mutating_skip(cfg, ep),
                ))
        return cases

    def evaluate(self, case, test, baseline) -> Judgement:
        return judge_access(case, test, baseline)
