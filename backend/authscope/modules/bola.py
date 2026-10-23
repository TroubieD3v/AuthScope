"""BOLA / IDOR: can identity X reach objects that belong to identity Y (same tenant)?"""
from __future__ import annotations

from ..config import ProjectConfig
from .base import Case, Judgement
from .object_access import evaluate_object_case, plan_object_cases


class BolaModule:
    name = "bola"
    title = "BOLA / IDOR"
    description = ("Compares the owner's baseline request with other identities requesting the same "
                   "object, and checks that list endpoints do not leak other users' objects.")

    def plan(self, cfg: ProjectConfig) -> list[Case]:
        return plan_object_cases(cfg, self.name)

    def evaluate(self, case, test, baseline) -> Judgement:
        return evaluate_object_case(case, test, baseline)
