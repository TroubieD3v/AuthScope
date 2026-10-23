"""Cross-Tenant access: data isolation between organizations in a multi-tenant API."""
from __future__ import annotations

from ..config import ProjectConfig
from .base import Case, Judgement
from .object_access import evaluate_object_case, plan_object_cases


class TenantModule:
    name = "tenant"
    title = "Cross-Tenant Access"
    description = ("Identities of one tenant request objects and lists belonging to another tenant. "
                   "Needs identities and resources with a tenant set.")

    def plan(self, cfg: ProjectConfig) -> list[Case]:
        return plan_object_cases(cfg, self.name)

    def evaluate(self, case, test, baseline) -> Judgement:
        return evaluate_object_case(case, test, baseline)
