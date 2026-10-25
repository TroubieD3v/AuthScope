"""Command line interface: `authscope run` (CI friendly), `authscope serve`, `authscope demo-config`."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from . import reports
from .config import ProjectConfig
from .http_engine import SecretStore
from .models import RunInfo
from .modules import REGISTRY
from .runner import TestRunner
from .storage import now


def _load(path: str) -> ProjectConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg = ProjectConfig.model_validate(data)
    base = Path(path).parent
    if isinstance(data, dict) and data.get("openapi"):
        from .openapi_import import endpoints_from_openapi, merge_endpoints, parse_document
        text = (base / data["openapi"]).read_text(encoding="utf-8")
        merge_endpoints(cfg, endpoints_from_openapi(parse_document(text)))
    if isinstance(data, dict) and data.get("postman"):
        from .openapi_import import merge_endpoints
        from .postman_import import endpoints_from_postman, parse_collection
        text = (base / data["postman"]).read_text(encoding="utf-8")
        merge_endpoints(cfg, endpoints_from_postman(parse_collection(text)))
    return cfg


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load(args.config)
    modules = args.module or [m for m in REGISTRY if m != "custom" or cfg.tests]
    if args.allow_mutating:
        cfg.target.allow_mutating = True
        if not (cfg.target.reset or cfg.target.acknowledge_no_reset):
            print("--allow-mutating needs a target.reset endpoint (or acknowledge_no_reset: true)", file=sys.stderr)
            return 2

    def progress(stats):
        if not args.quiet:
            print(f"\r{stats.done}/{stats.total} checks, {stats.requests} requests", end="", file=sys.stderr)

    runner = TestRunner(cfg, SecretStore(), "cli", modules, on_progress=progress)
    results = asyncio.run(runner.run())
    print(file=sys.stderr)
    run = RunInfo(id="cli", project_id="cli", status="completed", modules=modules, started_at=now(),
                  finished_at=now(), stats=runner.stats, extra={"warnings": runner.warnings})
    fmt = {"json": reports.to_json, "md": reports.to_markdown, "html": reports.to_html,
           "pytest": reports.to_pytest}[args.format]
    text = fmt(run, results, cfg)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"report written to {args.output}", file=sys.stderr)
    else:
        print(text)
    v = runner.stats.by_verdict
    print(f"violations={v.get('violation', 0)} review={v.get('needs_review', 0)} pass={v.get('pass', 0)} "
          f"inconclusive={v.get('inconclusive', 0)} skipped={v.get('skipped', 0)} errors={v.get('error', 0)}",
          file=sys.stderr)
    for w in runner.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 1 if v.get("violation", 0) else 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.i_know_this_is_exposed:
        print("Refusing to bind to a non-loopback address: the API can send requests to your test targets.\n"
              "Use --i-know-this-is-exposed if you put it behind your own access control.", file=sys.stderr)
        return 2
    uvicorn.run("authscope.api:factory", factory=True, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_demo_config(args: argparse.Namespace) -> int:
    from .demo import demo_config
    cfg = demo_config(args.base_url)
    print(yaml.safe_dump(cfg.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    p = argparse.ArgumentParser(prog="authscope", description="API authorization testing")
    p.add_argument("--version", action="version", version=f"authscope {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run checks from a YAML config (tokens come from environment variables)")
    r.add_argument("-c", "--config", required=True)
    r.add_argument("-m", "--module", action="append", choices=list(REGISTRY), help="repeatable; default: all")
    r.add_argument("-f", "--format", choices=["json", "md", "html", "pytest"], default="md")
    r.add_argument("-o", "--output")
    r.add_argument("--allow-mutating", action="store_true", help="also run state-changing tests (needs reset)")
    r.add_argument("-q", "--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("serve", help="start the web UI + API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--i-know-this-is-exposed", action="store_true")
    s.set_defaults(fn=cmd_serve)

    d = sub.add_parser("demo-config", help="print the YAML config for the bundled demo API")
    d.add_argument("--base-url", default="http://127.0.0.1:8000")
    d.set_defaults(fn=cmd_demo_config)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
