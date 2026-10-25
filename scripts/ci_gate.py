"""Authorization gate for CI: AuthScope must be right on BOTH sides.

    python scripts/ci_gate.py [--stand demo|ledger] --secure URL --vulnerable URL [--out reports/]

1. Secure demo (DEMO_VULNS=):        zero violations, zero needs-review, zero errors.
2. Vulnerable demo (all flaws on):   exactly the findings listed in examples/expected-findings.json
                                     (missing = false negative, extra = false positive).
3. Every object-level violation's evidence points at the reported object: the test request targets it and the
   response contains its id; the baseline was made by the object's owner.
4. No credential of the demo identities appears in any report format (JSON, Markdown, HTML, pytest).

Credentials come from examples/demo.env. Use --write-expected to regenerate the expected list after a reviewed
change to the demo API.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from authscope import reports  # noqa: E402
from authscope.config import ProjectConfig  # noqa: E402
from authscope.http_engine import SecretStore  # noqa: E402
from authscope.models import CheckResult, RunInfo  # noqa: E402
from authscope.runner import TestRunner  # noqa: E402
from authscope.storage import now  # noqa: E402

STANDS = {
    # stand: (config, credentials, expected findings, modules)
    "demo": ("demo.authscope.yaml", "demo.env", "expected-findings.json",
             ["unauth", "bola", "bfla", "bopla", "tenant", "custom"]),
    "ledger": ("ledger.authscope.yaml", "ledger.env", "expected-findings-ledger.json",
               ["unauth", "bola", "bfla", "bopla", "tenant"]),
}
CONFIG = ENV = EXPECTED = Path()
MODULES: list[str] = []
STAND_PREFIX = [""]


def load_env() -> dict[str, str]:
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    os.environ.update(values)
    return values


def config_for(url: str) -> ProjectConfig:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    data["target"]["base_url"] = url
    data["target"]["rate_limit_rps"] = 50
    return ProjectConfig.model_validate(data)


def run(url: str) -> tuple[ProjectConfig, RunInfo, list[CheckResult], TestRunner]:
    cfg = config_for(url)
    runner = TestRunner(cfg, SecretStore(), "ci", MODULES)
    results = asyncio.run(runner.run())
    info = RunInfo(id="ci", project_id="ci", status="completed", modules=MODULES, started_at=now(),
                   finished_at=now(), stats=runner.stats, extra={"warnings": runner.warnings})
    return cfg, info, results, runner


def key(r: CheckResult) -> str:
    return " | ".join([r.module, r.identity or "-", r.endpoint_key, r.resource or "-"])


def render_all(cfg, info, results, out: Path | None, name: str) -> dict[str, str]:
    texts = {
        "json": reports.to_json(info, results, cfg), "md": reports.to_markdown(info, results, cfg),
        "html": reports.to_html(info, results, cfg), "py": reports.to_pytest(info, results, cfg),
    }
    if out:
        out.mkdir(parents=True, exist_ok=True)
        for ext, text in texts.items():
            (out / f"{STAND_PREFIX[0]}{name}.{ext}").write_text(text, encoding="utf-8")
    return texts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secure", required=True)
    ap.add_argument("--vulnerable", required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--write-expected", action="store_true")
    ap.add_argument("--stand", choices=sorted(STANDS), default="demo")
    args = ap.parse_args()
    global CONFIG, ENV, EXPECTED, MODULES
    cfg_name, env_name, exp_name, MODULES = STANDS[args.stand]
    CONFIG, ENV, EXPECTED = (ROOT / "examples" / n for n in (cfg_name, env_name, exp_name))
    STAND_PREFIX[0] = "" if args.stand == "demo" else f"{args.stand}-"
    print(f"stand: {args.stand}")
    secrets = [v for v in load_env().values() if v]
    failures: list[str] = []

    # 1. secure side -------------------------------------------------------------------------------
    cfg, info, results, runner = run(args.secure)
    v = runner.stats.by_verdict
    print(f"secure:     {v}")
    for verdict in ("violation", "needs_review", "error"):
        for r in results:
            if r.verdict == verdict:
                failures.append(f"[secure] unexpected {verdict}: {key(r)} - {r.message}")
    if runner.warnings:
        failures += [f"[secure] warning: {w}" for w in runner.warnings]
    texts = render_all(cfg, info, results, args.out, "secure")

    # 2. vulnerable side ---------------------------------------------------------------------------
    vcfg, vinfo, vresults, vrunner = run(args.vulnerable)
    print(f"vulnerable: {vrunner.stats.by_verdict}")
    found = sorted(key(r) for r in vresults if r.verdict == "violation")
    if args.write_expected:
        EXPECTED.write_text(json.dumps({"violations": found}, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(found)} expected findings to {EXPECTED.relative_to(ROOT)}")
    expected = set(json.loads(EXPECTED.read_text(encoding="utf-8"))["violations"])
    failures += [f"[vulnerable] missed (false negative): {k}" for k in sorted(expected - set(found))]
    failures += [f"[vulnerable] unexpected (false positive?): {k}" for k in sorted(set(found) - expected)]
    for module in ("bola", "bfla", "bopla"):
        if not any(r.module == module and r.verdict == "violation" for r in vresults):
            failures.append(f"[vulnerable] no {module.upper()} violation found at all")
    if any(r.verdict in ("error", "needs_review") for r in vresults):
        failures.append("[vulnerable] errors or needs-review items in a run that should be unambiguous")

    # 3. evidence points at the reported object ----------------------------------------------------
    for r in vresults:
        if r.verdict != "violation" or not r.resource or r.variant == "list_leak":
            continue
        res = vcfg.resource(r.resource)
        ev = r.evidence
        if res is None or ev is None or ev.test is None:
            failures.append(f"[evidence] missing evidence for {key(r)}")
            continue
        path = ev.test.url.split("?")[0]
        segments = list(res.params.values()) or [res.id]
        if not all(f"/{seg}" in path for seg in segments):
            failures.append(f"[evidence] test request does not target {r.resource}: {ev.test.url}")
        body = ev.test.response_body or ""
        if res.match:
            if not all(str(val) in body for val in res.match.values()):
                failures.append(f"[evidence] response body of {key(r)} does not satisfy the match rules")
        elif res.id_field not in body or str(res.id) not in body:
            failures.append(f"[evidence] response body of {key(r)} does not contain {res.id_field}={res.id}")
        if ev.baseline and res.owner and ev.baseline.identity != res.owner:
            failures.append(f"[evidence] baseline of {key(r)} made by {ev.baseline.identity}, owner is {res.owner}")
    texts_v = render_all(vcfg, vinfo, vresults, args.out, "vulnerable")

    # 4. no credentials in any report --------------------------------------------------------------
    for side, rendered in (("secure", texts), ("vulnerable", texts_v)):
        for fmt, text in rendered.items():
            for s in secrets:
                if s in text:
                    failures.append(f"[secrets] a demo credential appears in the {side} {fmt} report")

    if failures:
        print(f"\nGATE FAILED ({len(failures)} problems):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nGATE PASSED: secure clean, {len(found)} expected violations found, evidence and masking verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
