"""Result models: HTTP exchanges, evidence, check results, run summaries."""
from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["pass", "violation", "needs_review", "inconclusive", "skipped", "error"]
Severity = Literal["info", "low", "medium", "high", "critical"]
Observed = Literal[
    "allowed_data", "allowed_empty", "allowed_ambiguous", "soft_denied", "denied",
    "rejected", "rate_limited", "redirect", "server_error", "transport_error", "skipped",
]
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
VERDICT_ORDER = {"pass": 0, "skipped": 1, "inconclusive": 2, "needs_review": 3, "error": 4, "violation": 5}


class HttpExchange(BaseModel):
    """A masked, storable request/response pair."""

    label: str
    identity: str | None = None
    method: str
    url: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str | None = None
    status: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str | None = None
    elapsed_ms: float = 0
    error: str | None = None


class Evidence(BaseModel):
    baseline: HttpExchange | None = None
    test: HttpExchange | None = None
    diff: list[str] = Field(default_factory=list)
    expected: str = ""
    observed: str = ""
    reproduction: list[str] = Field(default_factory=list)
    regression: dict[str, Any] | None = None  # machine-readable assertion for pytest export


class CheckResult(BaseModel):
    id: str = ""
    module: str
    name: str
    endpoint_key: str
    identity: str | None = None
    resource: str | None = None
    variant: str | None = None
    expected: Literal["allow", "deny"] | None = None
    observed: Observed = "skipped"
    verdict: Verdict
    severity: Severity = "info"
    message: str = ""
    evidence: Evidence | None = None

    def fingerprint(self) -> str:
        """Stable id across runs - used to track a finding between releases."""
        raw = "|".join([self.module, self.endpoint_key, self.identity or "", self.resource or "",
                        self.variant or ""])
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    @property
    def is_finding(self) -> bool:
        return self.verdict in ("violation", "needs_review")


class RunStats(BaseModel):
    total: int = 0
    done: int = 0
    requests: int = 0
    retries: int = 0
    backoff_s: float = 0.0
    by_verdict: dict[str, int] = Field(default_factory=dict)
    by_module: dict[str, dict[str, int]] = Field(default_factory=dict)


class RunInfo(BaseModel):
    id: str
    project_id: str
    status: Literal["queued", "running", "completed", "cancelled", "failed"]
    modules: list[str]
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    stats: RunStats = Field(default_factory=RunStats)
    extra: dict[str, Any] = Field(default_factory=dict)
