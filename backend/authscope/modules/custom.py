"""Explicit tests declared in the project config (`tests:` section)."""
from __future__ import annotations

from ..config import Endpoint, ProjectConfig
from .base import Case, Judgement, judge_access, mutating_skip


class CustomModule:
    name = "custom"
    title = "Custom tests"
    description = "Explicit allow/deny expectations from the `tests:` section of the config."

    def plan(self, cfg: ProjectConfig) -> list[Case]:
        cases: list[Case] = []
        for t in cfg.tests:
            ident = cfg.identity(t.identity)
            ep = Endpoint(method=t.method, path=t.path, body=t.body)
            res = cfg.resource(t.resource) if t.resource else None
            skip = None
            if ident is None:
                skip = f"unknown identity '{t.identity}'"
            elif t.resource and res is None:
                skip = f"unknown resource '{t.resource}'"
            else:
                skip = mutating_skip(cfg, ep)
            base = cfg.identity(t.baseline_identity) if t.baseline_identity else None
            cases.append(Case(
                module=self.name, name=t.name, endpoint=ep, identity=ident, expected=t.expected,
                resource=res, baseline_identity=base if not ep.mutating else None,
                reason="declared in config", skip_reason=skip, body=t.body,
                variant=t.name,
            ))
        return cases

    def evaluate(self, case, test, baseline) -> Judgement:
        return judge_access(case, test, baseline)
