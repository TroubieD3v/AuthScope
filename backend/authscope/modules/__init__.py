from __future__ import annotations

from .base import Module
from .bfla import BflaModule
from .bola import BolaModule
from .bopla import BoplaModule
from .custom import CustomModule
from .tenant import TenantModule
from .unauth import UnauthModule

REGISTRY: dict[str, Module] = {
    m.name: m
    for m in (UnauthModule(), BolaModule(), BflaModule(), BoplaModule(), TenantModule(), CustomModule())
}  # type: ignore[misc]

# Planned for later releases (shown as such in the UI, not runnable yet).
ROADMAP = {
    "mass_assignment": "Mass Assignment",
    "session": "Session Authorization",
}


def describe() -> list[dict[str, str]]:
    return [{"name": m.name, "title": m.title, "description": m.description} for m in REGISTRY.values()]
