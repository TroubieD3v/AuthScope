"""Report generation: JSON, Markdown, HTML (Jinja2, autoescaped) and pytest regression export."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ProjectConfig
from .evidence import pytest_snippet
from .models import SEVERITY_ORDER, VERDICT_ORDER, CheckResult, RunInfo

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape(["html", "j2"]))

VERDICT_LABEL = {"violation": "Policy violation", "needs_review": "Needs review", "pass": "Passed",
                 "inconclusive": "Inconclusive", "skipped": "Skipped", "error": "Error"}


def _sorted_findings(results: list[CheckResult]) -> list[CheckResult]:
    f = [r for r in results if r.is_finding]
    return sorted(f, key=lambda r: (-VERDICT_ORDER[r.verdict], -SEVERITY_ORDER[r.severity], r.endpoint_key))


def build(run: RunInfo, results: list[CheckResult], cfg: ProjectConfig) -> dict:
    return {
        "project": cfg.name, "target": cfg.target.base_url, "run": run.model_dump(),
        "summary": {
            "verdicts": dict(Counter(r.verdict for r in results)),
            "severities": dict(Counter(r.severity for r in results if r.is_finding)),
            "modules": {m: dict(Counter(r.verdict for r in results if r.module == m))
                        for m in sorted({r.module for r in results})},
            "total": len(results),
        },
        "findings": [r.model_dump() for r in _sorted_findings(results)],
        "passed": [r.model_dump(exclude={"evidence"}) for r in results if r.verdict == "pass"],
        "other": [r.model_dump(exclude={"evidence"}) for r in results
                  if r.verdict in ("skipped", "inconclusive", "error")],
        "warnings": run.extra.get("warnings", []),
    }


def to_json(run: RunInfo, results: list[CheckResult], cfg: ProjectConfig) -> str:
    return json.dumps(build(run, results, cfg), indent=2, ensure_ascii=False)


def _fence(text: str | None, lang: str = "") -> str:
    return f"```{lang}\n{text or ''}\n```"


def _exchange_md(title: str, ex) -> str:
    if ex is None:
        return ""
    req_h = "\n".join(f"{k}: {v}" for k, v in ex.request_headers.items())
    body = f"\n\n{ex.request_body}" if ex.request_body else ""
    resp = f"HTTP {ex.status}" if ex.status is not None else f"ERROR {ex.error}"
    return (f"**{title}** - `{ex.identity or 'anonymous'}`\n\n"
            f"{_fence(f'{ex.method} {ex.url}' + chr(10) + req_h + body, 'http')}\n"
            f"{_fence(resp + chr(10) + (ex.response_body or ''), 'http')}\n")


def to_markdown(run: RunInfo, results: list[CheckResult], cfg: ProjectConfig) -> str:
    data = build(run, results, cfg)
    v = data["summary"]["verdicts"]
    lines = [
        f"# AuthScope report - {cfg.name}", "",
        f"- Target: `{cfg.target.base_url}`",
        f"- Run: `{run.id}` ({run.status}), started {run.started_at}",
        f"- Modules: {', '.join(run.modules)}",
        f"- Checks: {len(results)} - **{v.get('violation', 0)} violations**, "
        f"{v.get('needs_review', 0)} need review, {v.get('pass', 0)} passed, "
        f"{v.get('inconclusive', 0)} inconclusive, {v.get('skipped', 0)} skipped, {v.get('error', 0)} errors",
        "", "Tokens and sensitive values are masked. Reproduction commands read tokens from environment variables.", "",
    ]
    for w in data["warnings"]:
        lines.append(f"> Warning: {w}")
    lines += ["", "## Summary by module", "", "| Module | Violations | Review | Passed | Other |", "|---|---|---|---|---|"]
    for m, c in data["summary"]["modules"].items():
        other = sum(c.get(k, 0) for k in ("inconclusive", "skipped", "error"))
        lines.append(f"| {m} | {c.get('violation', 0)} | {c.get('needs_review', 0)} | {c.get('pass', 0)} | {other} |")

    findings = _sorted_findings(results)
    lines += ["", f"## Findings ({len(findings)})", ""]
    if not findings:
        lines.append("No violations or review items were found.")
    for i, r in enumerate(findings, 1):
        ev = r.evidence
        lines += [f"### {i}. [{r.severity.upper()}] {VERDICT_LABEL[r.verdict]} - {r.name}", "",
                  f"- Module: `{r.module}`  |  Endpoint: `{r.endpoint_key}`  |  Identity: `{r.identity}`"
                  + (f"  |  Resource: `{r.resource}`" if r.resource else ""),
                  f"- Finding id: `{r.id}`", f"- {r.message}", ""]
        if ev:
            lines += [f"**Expected policy:** {ev.expected}", ""]
            if ev.diff:
                lines += ["**Differences / analysis**", ""] + [f"- {d}" for d in ev.diff] + [""]
            lines += [_exchange_md("Baseline", ev.baseline), _exchange_md("Test", ev.test)]
            if ev.reproduction:
                lines += ["**Reproduce**", "", _fence("\n\n".join(ev.reproduction), "bash"), ""]

    passed = [r for r in results if r.verdict == "pass"]
    lines += [f"## Passed checks ({len(passed)})", "", "| Module | Check | Result |", "|---|---|---|"]
    for r in passed:
        lines.append(f"| {r.module} | {r.name.replace('|', '/')} | {r.message.replace('|', '/')[:90]} |")
    rest = [r for r in results if r.verdict in ("inconclusive", "skipped", "error")]
    if rest:
        lines += ["", f"## Inconclusive, skipped and errors ({len(rest)})", "", "| Verdict | Check | Reason |", "|---|---|---|"]
        for r in rest:
            lines.append(f"| {r.verdict} | {r.name.replace('|', '/')} | {r.message.replace('|', '/')[:110]} |")
    return "\n".join(lines) + "\n"


def to_html(run: RunInfo, results: list[CheckResult], cfg: ProjectConfig) -> str:
    return _env.get_template("report.html.j2").render(
        d=build(run, results, cfg), findings=_sorted_findings(results),
        passed=[r for r in results if r.verdict == "pass"],
        rest=[r for r in results if r.verdict in ("inconclusive", "skipped", "error")],
        labels=VERDICT_LABEL)


_PYTEST_HEADER = '''"""Authorization regression tests generated by AuthScope (run {run}).

Each test asserts the *expected* policy, so it fails while the problem exists and passes once it is fixed.
Tokens are read from environment variables - never commit them.
"""
import os

import httpx

BASE_URL = os.environ.get("AUTHSCOPE_BASE_URL", "{base}")
DENIED = (401, 403, 404)


def _ids(data, key):
    if isinstance(data, dict):
        found = {{str(data[key])}} if key in data and not isinstance(data[key], (dict, list)) else set()
        return found.union(*[_ids(v, key) for v in data.values()])
    if isinstance(data, list):
        return set().union(*[_ids(v, key) for v in data]) if data else set()
    return set()


def _norm(s):
    return s.replace("_", "").replace("-", "").lower()


def _has_field(data, name):
    if isinstance(data, dict):
        return any((_norm(k) == _norm(name) and v not in (None, "", [], {{}})) or _has_field(v, name)
                   for k, v in data.items())
    if isinstance(data, list):
        return any(_has_field(v, name) for v in data)
    return False


'''


def to_pytest(run: RunInfo, results: list[CheckResult], cfg: ProjectConfig, only_findings: bool = True) -> str:
    out = [_PYTEST_HEADER.format(run=run.id, base=cfg.target.base_url)]
    chosen = [r for r in results if (r.is_finding if only_findings else r.verdict in ("pass", "violation", "needs_review"))
              and r.evidence and r.evidence.test and r.evidence.regression]
    if not chosen:
        out.append("# No findings to export - nothing to regress.\n")
    for i, r in enumerate(chosen, 1):
        ev, reg = r.evidence, r.evidence.regression  # type: ignore[union-attr]
        t = ev.test  # type: ignore[union-attr]
        ident = cfg.identity(r.identity) if r.identity else None
        mode = reg.get("mode") or ("invalid" if r.variant == "invalid_token" else
                                   "none" if ident is None or ident.anonymous else "identity")
        base = pytest_snippet(i, r.module, r.name, t.method, t.url.replace(cfg.target.base_url, ""),  # type: ignore[union-attr]
                              ident, mode, "deny" if reg["type"] != "allow" else "allow", t.request_body)
        if reg["type"] == "list_leak":
            base = base.replace("assert resp.status_code in DENIED",
                                f"assert resp.status_code < 300 and not (_ids(resp.json(), {reg['id_field']!r}) "
                                f"& set({reg['ids']!r}))")
        elif reg["type"] == "fields_absent":
            base = base.replace("assert resp.status_code in DENIED",
                                "assert resp.status_code < 300\n    body = resp.json()\n    "
                                f"assert not [f for f in {reg['fields']!r} if _has_field(body, f)]")
        out.append(f"# finding {r.id} - {r.severity}\n" + base)
    return "\n\n".join(out)
