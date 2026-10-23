"""Test runner: plans module cases, executes them under safety limits, builds evidence."""
from __future__ import annotations

import asyncio
import os
import re
from collections import Counter
from typing import Any, Callable

from .compare import classify, diff_summary
from .config import Identity, ProjectConfig
from .evidence import curl_command
from .http_engine import RawResponse, Requester, SecretStore, render_path
from .masking import Masker
from .models import CheckResult, Evidence, RunStats
from .modules import REGISTRY
from .modules.base import Case, Judgement
from .safety import BudgetExceeded, SafetyError


class TestRunner:
    __test__ = False  # not a pytest class

    def __init__(
        self, cfg: ProjectConfig, secrets: SecretStore, project_id: str, modules: list[str],
        on_result: Callable[[CheckResult], None] | None = None,
        on_progress: Callable[[RunStats], None] | None = None,
    ) -> None:
        unknown = [m for m in modules if m not in REGISTRY]
        if unknown:
            raise ValueError(f"unknown module(s): {', '.join(unknown)}")
        self.cfg, self.modules = cfg, modules
        self.secrets, self.project_id = secrets, project_id
        self.on_result, self.on_progress = on_result, on_progress
        self.cancel_event = asyncio.Event()
        self.stats = RunStats()
        self.warnings: list[str] = []
        self.results: list[CheckResult] = []
        self._baselines: dict[tuple, RawResponse | None] = {}
        self._reset_failed = False
        self._login_tokens: dict[str, str] = {}  # obtained via login flows, this run only

    def cancel(self) -> None:
        self.cancel_event.set()

    # ----------------------------------------------------------------------------------
    def _resolve(self, identity: Identity) -> str | None:
        """Explicit token (UI / env) first, then a token obtained by this run's login flow."""
        return self.secrets.get(self.project_id, identity) or self._login_tokens.get(identity.name)

    async def run(self) -> list[CheckResult]:
        self.requester = Requester(self.cfg.target, self._resolve)
        self.masker = Masker()
        try:
            await self._login_all()
            masked = self.requester.secret_values(self.cfg.identities)
            for i in self.cfg.identities:
                if i.login and (pw := self.secrets.get(self.project_id, i, "password")):
                    masked[f"{i.name}:password"] = pw
            self.masker = Masker(masked)
            cases = [c for m in self.modules for c in REGISTRY[m].plan(self.cfg)]
            self.stats.total = len(cases)
            self._progress()
            self._flag_missing_credentials(cases)
            await self._run_baselines([c for c in cases if not c.skip_reason])

            sem = asyncio.Semaphore(self.cfg.target.concurrency)

            async def guarded(case: Case) -> None:
                async with sem:
                    await self._execute(case)

            read_cases = [c for c in cases if not c.endpoint.mutating]
            write_cases = [c for c in cases if c.endpoint.mutating]
            await asyncio.gather(*(guarded(c) for c in read_cases))
            for c in write_cases:  # state-changing tests run strictly one by one
                await self._execute(c)
        finally:
            self.stats.requests = self.requester.budget.used
            await self.requester.aclose()
            self._progress()
        return self.results

    # ----------------------------------------------------------------------------------
    async def _login_all(self) -> None:
        for ident in self.cfg.identities:
            if ident.anonymous or not ident.login or self.secrets.get(self.project_id, ident):
                continue
            login = ident.login
            password = self.secrets.get(self.project_id, ident, "password")
            missing: list[str] = []

            def fill(value: Any) -> Any:
                if isinstance(value, dict):
                    return {k: fill(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [fill(v) for v in value]
                if not isinstance(value, str):
                    return value

                def sub(m: re.Match) -> str:
                    name = m.group(1)
                    val = password if name == "password" else os.environ.get(name)
                    if val is None:
                        missing.append(ident.password_env or "password" if name == "password" else name)
                        return ""
                    return val
                return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, value)

            body = fill(login.body)
            if missing:
                self.warnings.append(f"login for '{ident.name}' skipped: set {', '.join(missing)}")
                continue
            try:
                raw = await self.requester.send(login.method, login.path, body=body, mode="none",
                                                label=f"login ({ident.name})", login=True)
            except SafetyError as exc:
                self.warnings.append(f"login for '{ident.name}' refused: {exc}")
                continue
            token: Any = raw.json
            for part in login.token_path.split("."):
                token = token.get(part) if isinstance(token, dict) else None
            if raw.error or not (200 <= (raw.status or 0) < 300) or not isinstance(token, str) or not token:
                why = raw.error or f"HTTP {raw.status}" + ("" if token else f", no '{login.token_path}' in response")
                self.warnings.append(f"login for '{ident.name}' failed: {why}")
                continue
            self._login_tokens[ident.name] = token

    def _flag_missing_credentials(self, cases: list[Case]) -> None:
        missing = {i.name for i in self.cfg.identities if not i.anonymous and not self._resolve(i)}
        if missing:
            self.warnings.append("No credential available for: " + ", ".join(sorted(missing)))
        for c in cases:
            if c.skip_reason:
                continue
            needed = [c.identity] if c.mode == "identity" and c.identity else []
            if c.baseline_identity:
                needed.append(c.baseline_identity)
            lacking = [i.name for i in needed if i.name in missing]
            if lacking:
                c.skip_reason = f"no credential for identity '{lacking[0]}' (set {self._env_name(lacking[0])})"

    def _env_name(self, name: str) -> str:
        ident = self.cfg.identity(name)
        return ident.token_env if ident and ident.token_env else "its token"

    def _request_parts(self, case: Case):
        ep = case.endpoint
        path = render_path(ep.path, self.cfg.path_values(ep, case.resource))
        body = case.body if case.body is not None else ep.body
        return ep.method, path, (ep.query or None), (body if ep.mutating else None)

    def _baseline_key(self, case: Case) -> tuple | None:
        if not case.baseline_identity:
            return None
        return (case.endpoint.key, case.resource.ref if case.resource else None, case.baseline_identity.name)

    async def _run_baselines(self, cases: list[Case]) -> None:
        keys: dict[tuple, Case] = {}
        for c in cases:
            k = self._baseline_key(c)
            if k and k not in keys:
                keys[k] = c
        for k, c in keys.items():
            if self.cancel_event.is_set():
                break
            method, path, query, body = self._request_parts(c)
            if "{" in path:
                self._baselines[k] = None
                continue
            try:
                self._baselines[k] = await self.requester.send(
                    method, path, identity=c.baseline_identity, query=query, body=body,
                    label=f"baseline ({c.baseline_identity.name})")
            except BudgetExceeded:
                self._baselines[k] = None
                self.cancel_event.set()
                self.warnings.append("request budget exhausted during baselines")
            except SafetyError as exc:
                self._baselines[k] = None
                self.warnings.append(str(exc))

    # ----------------------------------------------------------------------------------
    async def _execute(self, case: Case) -> None:
        result = await self._execute_inner(case)
        result.id = result.fingerprint()
        self.results.append(result)
        self.stats.done += 1
        self.stats.by_verdict[result.verdict] = self.stats.by_verdict.get(result.verdict, 0) + 1
        mod = self.stats.by_module.setdefault(result.module, {})
        mod[result.verdict] = mod.get(result.verdict, 0) + 1
        self.stats.requests = self.requester.budget.used
        if self.on_result:
            self.on_result(result)
        self._progress()

    def _result(self, case: Case, j: Judgement, evidence: Evidence | None = None) -> CheckResult:
        return CheckResult(
            module=case.module, name=case.name, endpoint_key=case.endpoint.key,
            identity=case.identity_name, resource=case.resource.ref if case.resource else None,
            variant=case.variant, expected=case.expected,  # type: ignore[arg-type]
            observed=j.observed, verdict=j.verdict, severity=j.severity,  # type: ignore[arg-type]
            message=j.message, evidence=evidence,
        )

    async def _execute_inner(self, case: Case) -> CheckResult:
        def skipped(reason: str) -> CheckResult:
            return self._result(case, Judgement("skipped", "skipped", reason))

        if self.cancel_event.is_set():
            return skipped("run cancelled")
        if case.skip_reason:
            return skipped(case.skip_reason)
        if case.endpoint.mutating and self._reset_failed:
            return skipped("an earlier reset of the test data failed; state-changing tests stopped")

        method, path, query, body = self._request_parts(case)
        if "{" in path:
            return skipped(f"path parameter in '{case.endpoint.path}' has no value (set endpoint params)")

        bkey = self._baseline_key(case)
        baseline = self._baselines.get(bkey) if bkey else None
        same_as_baseline = (bkey is not None and case.mode == "identity" and case.identity is not None
                            and case.identity.name == case.baseline_identity.name)  # type: ignore[union-attr]
        try:
            if same_as_baseline and baseline is not None:
                test = baseline
                test.label = "test (owner = baseline)"
            else:
                test = await self.requester.send(method, path, identity=case.identity, mode=case.mode,
                                                 query=query, body=body, label="test")
            if case.endpoint.mutating:
                await self._reset()
        except BudgetExceeded as exc:
            self.cancel_event.set()
            self.warnings.append(str(exc))
            return skipped(str(exc))
        except SafetyError as exc:
            return self._result(case, Judgement("error", "transport_error", f"Blocked by safety rule: {exc}"))

        # A failed baseline makes the comparison meaningless for everyone but the owner.
        if baseline is not None and not same_as_baseline:
            bobs = classify(baseline)  # must simply be a successful, non-empty answer
            if bobs.kind != "allowed_data":
                j = Judgement("inconclusive", "skipped",
                              f"Baseline request by '{case.baseline_identity.name}' failed ({bobs.detail}); "  # type: ignore[union-attr]
                              "check that the resource exists and the owner is configured correctly")
                return self._result(case, j, Evidence(test=test.exchange(self.masker),
                                                      baseline=baseline.exchange(self.masker)))
        j = REGISTRY[case.module].evaluate(case, test, None if same_as_baseline else baseline)
        evidence = self._evidence(case, j, test, None if same_as_baseline else baseline)
        return self._result(case, j, evidence)

    def _evidence(self, case: Case, j: Judgement, test: RawResponse, baseline: RawResponse | None) -> Evidence:
        res = case.resource
        obs = classify(test, baseline=baseline, id_field=res.id_field if res else "id",
                       resource_id=res.id if res else None)
        diff = j.diff or diff_summary(baseline, test, obs)
        repro = []
        if baseline is not None and case.baseline_identity:
            repro.append("# 1) baseline - the owner's request\n" + curl_command(baseline, case.baseline_identity, "identity"))
        repro.append(("# 2) test request\n" if repro else "") + curl_command(test, case.identity, case.mode))
        who = case.identity_name or "anonymous"
        return Evidence(
            baseline=baseline.exchange(self.masker) if baseline else None,
            test=test.exchange(self.masker), diff=diff,
            expected=f"{case.expected} for '{who}' - {case.reason}" if case.expected else "",
            observed=f"{j.observed}: {j.message}", reproduction=[self.masker.text(r) for r in repro],
            regression=self._regression(case),
        )

    @staticmethod
    def _regression(case: Case) -> dict | None:
        if case.kind == "list_leak":
            return {"type": "list_leak", "ids": [r.split(":", 1)[1] for r in case.extra["foreign"]],
                    "id_field": case.extra["id_field"]}
        if case.kind == "fields":
            return {"type": "fields_absent", "fields": case.extra["restricted"]} if case.extra["restricted"] else None
        return {"type": case.expected, "mode": case.mode} if case.expected else None

    async def _reset(self) -> None:
        reset = self.cfg.target.reset
        if not reset:
            return
        ident = self.cfg.identity(reset.identity) if reset.identity else None
        try:
            raw = await self.requester.send(reset.method, reset.path, identity=ident, label="reset")
            if raw.error or (raw.status or 0) >= 400:
                raise SafetyError(raw.error or f"reset returned HTTP {raw.status}")
        except SafetyError as exc:
            self._reset_failed = True
            self.warnings.append(f"reset failed: {exc}")

    def _progress(self) -> None:
        if self.on_progress:
            self.on_progress(self.stats)


def summarize(results: list[CheckResult]) -> dict[str, int]:
    return dict(Counter(r.verdict for r in results))


__all__ = ["TestRunner", "summarize", "Identity"]
