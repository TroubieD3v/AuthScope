"""FastAPI backend. Bind to localhost only - this service can send requests to configured targets."""
from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, ValidationError

from . import __version__, reports
from .config import Endpoint, Identity, Override, ProjectConfig, Resource
from .demo import demo_config, demo_secrets
from .http_engine import MAX_RESPONSE_BYTES, SecretStore
from .modules import REGISTRY, ROADMAP, describe
from .models import RunInfo
from .openapi_import import ImportErrorInfo, endpoints_from_openapi, merge_endpoints, parse_document
from .postman_import import endpoints_from_postman, is_postman, parse_collection
from .policy import decide, matrix_cell
from .runner import TestRunner
from .safety import SafetyError, TargetGuard
from .storage import Store, now as now_iso


class RunRequest(BaseModel):
    modules: list[str] = ["unauth", "bola", "bfla", "bopla", "tenant", "custom"]


class ImportRequest(BaseModel):
    url: str | None = None
    content: str | None = None
    replace: bool = False


class SecretRequest(BaseModel):
    token: str


def create_app(store: Store | None = None, secrets: SecretStore | None = None) -> FastAPI:
    store = store or Store()
    secrets = secrets or SecretStore()
    store.fail_stale_runs()
    active: dict[str, TestRunner] = {}
    tasks: set[asyncio.Task] = set()

    app = FastAPI(title="AuthScope", version=__version__)
    ui_hosts = ["localhost", "127.0.0.1", "[::1]", "testserver"] + [
        h for h in os.environ.get("AUTHSCOPE_ALLOWED_UI_HOSTS", "").split(",") if h]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ui_hosts)  # DNS-rebinding protection
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    # -- helpers ---------------------------------------------------------------------------
    def project(pid: str) -> ProjectConfig:
        cfg = store.get_project(pid)
        if cfg is None:
            raise HTTPException(404, "project not found")
        return cfg

    def save(pid: str, cfg: ProjectConfig) -> ProjectConfig:
        store.update_project(pid, cfg)
        return cfg

    def project_view(pid: str, cfg: ProjectConfig) -> dict[str, Any]:
        data = cfg.model_dump()
        data["id"] = pid
        for i in data["identities"]:
            ident = cfg.identity(i["name"])
            if ident is None:
                continue
            i["secret_source"] = secrets.source(pid, ident)
            i["has_secret"] = i["secret_source"] in ("none", "runtime", "env", "login")
            i["password_source"] = secrets.source(pid, ident, "password") if ident.login else None
        return data

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError):
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors(include_url=False, include_context=False)]})

    # -- meta ------------------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__,
                "demo_url": os.environ.get("AUTHSCOPE_DEMO_URL", "http://127.0.0.1:8000")}

    @app.get("/api/modules")
    def modules():
        return {"modules": describe(), "roadmap": [{"name": k, "title": v} for k, v in ROADMAP.items()]}

    # -- projects ------------------------------------------------------------------------------
    @app.get("/api/projects")
    def list_projects():
        return store.list_projects()

    @app.post("/api/projects", status_code=201)
    def create_project(cfg: ProjectConfig):
        pid = store.create_project(cfg)
        return project_view(pid, cfg)

    @app.post("/api/projects/demo", status_code=201)
    def create_demo(base_url: str = Body("http://127.0.0.1:8000", embed=True)):
        cfg = demo_config(base_url)
        pid = store.create_project(cfg)
        for (name, kind), value in demo_secrets().items():
            secrets.set(pid, name, value, kind)
        return project_view(pid, cfg)

    @app.post("/api/projects/import-yaml", status_code=201)
    def import_yaml(content: str = Body(..., embed=True)):
        try:
            cfg = ProjectConfig.model_validate(yaml.safe_load(content))
        except yaml.YAMLError as exc:
            raise HTTPException(422, f"invalid YAML: {exc}") from exc
        return project_view(store.create_project(cfg), cfg)

    @app.get("/api/projects/{pid}")
    def get_project(pid: str):
        return project_view(pid, project(pid))

    @app.put("/api/projects/{pid}")
    def put_project(pid: str, cfg: ProjectConfig):
        project(pid)
        return project_view(pid, save(pid, cfg))

    @app.delete("/api/projects/{pid}", status_code=204)
    def delete_project(pid: str):
        project(pid)
        store.delete_project(pid)

    @app.get("/api/projects/{pid}/export.yaml")
    def export_yaml(pid: str):
        cfg = project(pid)
        text = yaml.safe_dump(cfg.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)
        return PlainTextResponse(text, media_type="application/x-yaml",
                                 headers={"Content-Disposition": 'attachment; filename="authscope.yaml"'})

    # -- OpenAPI import ------------------------------------------------------------------------
    @app.post("/api/projects/{pid}/import")
    @app.post("/api/projects/{pid}/import/openapi")
    async def import_openapi(pid: str, req: ImportRequest):
        cfg = project(pid)
        content = req.content
        if not content and req.url:
            guard = TargetGuard(cfg.target)
            try:
                pinned = await guard.pin(req.url)
            except SafetyError as exc:
                raise HTTPException(400, f"refused: {exc}") from exc
            try:
                async with httpx.AsyncClient(timeout=cfg.target.timeout_s, follow_redirects=False, trust_env=False,
                                             verify=cfg.target.verify_tls) as c:
                    async with c.stream("GET", pinned.url, headers={"Host": pinned.host},
                                        extensions=pinned.extensions) as resp:
                        if resp.status_code != 200:
                            raise HTTPException(400, f"spec URL answered HTTP {resp.status_code}")
                        buf = b""
                        async for chunk in resp.aiter_bytes():
                            buf += chunk
                            if len(buf) > MAX_RESPONSE_BYTES * 5:
                                raise HTTPException(400, "spec is too large")
                content = buf.decode("utf-8", errors="replace")
            except httpx.HTTPError as exc:
                raise HTTPException(400, f"could not fetch spec: {exc}") from exc
        if not content:
            raise HTTPException(422, "provide 'url' or 'content'")
        try:
            probe = json.loads(content)
        except ValueError:
            probe = None
        try:
            if is_postman(probe):
                doc, kind = parse_collection(content), "Postman collection"
                imported = endpoints_from_postman(doc)
                warnings = []
            else:
                doc, kind = parse_document(content), "OpenAPI"
                imported = endpoints_from_openapi(doc)
                schemes = (doc.get("components", {}) or {}).get("securitySchemes") or doc.get("securityDefinitions")
                warnings = [] if schemes else [
                    "The spec declares no securitySchemes: every endpoint was treated as requiring authentication."]
        except ImportErrorInfo as exc:
            raise HTTPException(422, str(exc)) from exc
        result = merge_endpoints(cfg, imported, replace=req.replace)
        save(pid, cfg)
        warnings.append("Access rules are inferred - review them in the API Explorer and the Permission Matrix.")
        result["format"] = kind
        return {**result, "title": (doc.get("info") or {}).get("title"), "warnings": warnings}

    # -- endpoints / identities / resources / overrides (granular edits for the UI) --------------
    @app.put("/api/projects/{pid}/endpoints")
    def put_endpoint(pid: str, ep: Endpoint):
        cfg = project(pid)
        ep.inferred = False
        cur = cfg.endpoint(ep.key)
        if cur:
            cfg.endpoints[cfg.endpoints.index(cur)] = ep
        else:
            cfg.endpoints.append(ep)
        save(pid, cfg)
        return ep

    @app.delete("/api/projects/{pid}/endpoints", status_code=204)
    def delete_endpoint(pid: str, key: str = Query(...)):
        cfg = project(pid)
        cfg.endpoints = [e for e in cfg.endpoints if e.key != key]
        save(pid, cfg)

    @app.put("/api/projects/{pid}/identities")
    def put_identity(pid: str, ident: Identity):
        cfg = project(pid)
        cur = cfg.identity(ident.name)
        if cur:
            cfg.identities[cfg.identities.index(cur)] = ident
        else:
            cfg.identities.append(ident)
        save(pid, cfg)
        return project_view(pid, cfg)

    @app.delete("/api/projects/{pid}/identities/{name}", status_code=204)
    def delete_identity(pid: str, name: str):
        cfg = project(pid)
        cfg.identities = [i for i in cfg.identities if i.name != name]
        cfg.overrides = [o for o in cfg.overrides if o.identity != name]
        secrets.delete(pid, name)
        save(pid, cfg)

    @app.put("/api/projects/{pid}/identities/{name}/secret", status_code=204)
    def set_secret(pid: str, name: str, body: SecretRequest,
                   kind: str = Query("token", pattern="^(token|password)$")):
        ident = project(pid).identity(name)
        if ident is None or ident.anonymous:
            raise HTTPException(404, "identity not found or anonymous")
        if not body.token.strip():
            raise HTTPException(422, "empty value")
        secrets.set(pid, name, body.token.strip(), kind)  # kept in memory only, never stored

    @app.delete("/api/projects/{pid}/identities/{name}/secret", status_code=204)
    def clear_secret(pid: str, name: str, kind: str | None = Query(None, pattern="^(token|password)$")):
        secrets.delete(pid, name, kind)

    @app.put("/api/projects/{pid}/resources")
    def put_resources(pid: str, resources: list[Resource]):
        cfg = project(pid)
        cfg.resources = resources
        save(pid, cfg)
        return resources

    @app.put("/api/projects/{pid}/overrides")
    def put_override(pid: str, ov: Override, clear: bool = Query(False)):
        cfg = project(pid)
        cfg.overrides = [o for o in cfg.overrides
                         if not (o.endpoint == ov.endpoint and o.identity == ov.identity and o.resource == ov.resource)]
        if not clear:
            cfg.overrides.append(ov)
        save(pid, cfg)
        return cfg.overrides

    # -- matrix / dashboard --------------------------------------------------------------------
    @app.get("/api/projects/{pid}/matrix")
    def matrix(pid: str, run_id: str | None = None):
        cfg = project(pid)
        run = store.get_run(run_id) if run_id else store.latest_run(pid)
        results = store.results(run.id) if run else []
        by_cell: dict[tuple[str, str], list[str]] = {}
        anon_names = {i.name for i in cfg.identities if i.anonymous}
        for r in results:
            who = r.identity or "anonymous"
            if who == "anonymous" and anon_names:
                who = sorted(anon_names)[0]
            by_cell.setdefault((r.endpoint_key, who), []).append(r.verdict)
        rows = []
        for ep in cfg.endpoints:
            cells = {}
            for ident in cfg.identities:
                verdicts = by_cell.get((ep.key, ident.name), [])
                worst = None
                for v in ("violation", "error", "needs_review", "inconclusive", "pass", "skipped"):
                    if v in verdicts:
                        worst = v
                        break
                cells[ident.name] = {
                    "expected": matrix_cell(cfg, ep, ident) if ep.enabled else "off",
                    "overridden": any(o.endpoint == ep.key and o.identity == ident.name for o in cfg.overrides),
                    "actual": dict(Counter(verdicts)), "worst": worst,
                }
            rows.append({"endpoint": ep.key, "method": ep.method, "path": ep.path, "access": ep.access,
                         "enabled": ep.enabled, "inferred": ep.inferred, "cells": cells})
        return {"identities": [{"name": i.name, "role": i.role, "tenant": i.tenant} for i in cfg.identities],
                "rows": rows, "run_id": run.id if run else None}

    @app.get("/api/projects/{pid}/dashboard")
    def dashboard(pid: str):
        cfg = project(pid)
        runs = store.list_runs(pid, 10)
        latest = next((r for r in runs if r.status in ("completed", "cancelled")), None)
        results = store.results(latest.id) if latest else []
        findings = [r for r in results if r.is_finding]
        return {
            "endpoints": len([e for e in cfg.endpoints if e.enabled]),
            "identities": len([i for i in cfg.identities if not i.anonymous]),
            "resources": len(cfg.resources),
            "latest_run": latest.model_dump() if latest else None,
            "verdicts": dict(Counter(r.verdict for r in results)),
            "severities": dict(Counter(r.severity for r in findings)),
            "modules": {m: dict(Counter(r.verdict for r in results if r.module == m))
                        for m in sorted({r.module for r in results})},
            "history": [{"id": r.id, "status": r.status, "started_at": r.started_at,
                         "violations": r.stats.by_verdict.get("violation", 0),
                         "review": r.stats.by_verdict.get("needs_review", 0),
                         "passed": r.stats.by_verdict.get("pass", 0)} for r in runs],
        }

    # -- runs ------------------------------------------------------------------------------------
    @app.post("/api/projects/{pid}/runs", status_code=202)
    async def start_run(pid: str, req: RunRequest):
        cfg = project(pid)
        bad = [m for m in req.modules if m not in REGISTRY]
        if bad or not req.modules:
            raise HTTPException(422, f"unknown or empty module list: {bad}")
        if any(r.project_id == pid for r in active.values()):
            raise HTTPException(409, "a run is already in progress for this project")
        run = store.create_run(pid, req.modules, cfg)
        counter = {"n": 0}

        def on_result(res):
            store.add_result(run.id, counter["n"], res)
            counter["n"] += 1

        def on_progress(stats):
            run.stats = stats.model_copy(deep=True)
            store.update_run(run)

        runner = TestRunner(cfg, secrets, pid, req.modules, on_result, on_progress)
        active[run.id] = runner

        async def go() -> None:
            run.status = "running"
            store.update_run(run)
            try:
                await runner.run()
                run.status = "cancelled" if runner.cancel_event.is_set() else "completed"
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
            run.stats = runner.stats
            run.extra["warnings"] = runner.warnings
            run.finished_at = now_iso()
            store.update_run(run)
            active.pop(run.id, None)

        task = asyncio.create_task(go())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return run

    @app.get("/api/projects/{pid}/runs")
    def runs(pid: str):
        project(pid)
        return store.list_runs(pid, 50)

    def get_run(rid: str) -> RunInfo:
        run = store.get_run(rid)
        if run is None:
            raise HTTPException(404, "run not found")
        return run

    @app.get("/api/runs/{rid}")
    def run_status(rid: str):
        return get_run(rid)

    @app.post("/api/runs/{rid}/cancel", status_code=202)
    def cancel(rid: str):
        get_run(rid)
        runner = active.get(rid)
        if runner:
            runner.cancel()
        return {"cancelling": runner is not None}

    @app.get("/api/runs/{rid}/results")
    def results(rid: str, only: str = "all", module: str | None = None, verdict: str | None = None):
        get_run(rid)
        verdicts = [verdict] if verdict else (["violation", "needs_review"] if only == "findings" else None)
        out = store.results(rid, verdicts, module)
        light = only != "findings"
        return [r.model_dump(exclude={"evidence"} if light else set()) for r in out]

    @app.get("/api/runs/{rid}/results/{result_id}")
    def result_detail(rid: str, result_id: str):
        r = store.result(rid, result_id)
        if r is None:
            raise HTTPException(404, "result not found")
        return r

    @app.get("/api/runs/{rid}/diff")
    def diff(rid: str, against: str = Query(...)):
        """Authorization regression: findings new / fixed / unchanged versus another run."""
        get_run(rid), get_run(against)
        now_f = {r.id: r for r in store.results(rid, ["violation", "needs_review"])}
        old_f = {r.id: r for r in store.results(against, ["violation", "needs_review"])}
        brief = lambda rs: [{"id": r.id, "name": r.name, "module": r.module, "verdict": r.verdict,  # noqa: E731
                             "severity": r.severity} for r in rs]
        return {"new": brief(r for k, r in now_f.items() if k not in old_f),
                "fixed": brief(r for k, r in old_f.items() if k not in now_f),
                "unchanged": brief(r for k, r in now_f.items() if k in old_f)}

    @app.get("/api/runs/{rid}/report")
    def report(rid: str, format: str = Query("json", pattern="^(json|md|html|pytest)$"), download: bool = False):
        run = get_run(rid)
        cfg = store.run_config(rid) or project(run.project_id)
        res = store.results(rid)
        if format == "json":
            body, mime, ext = reports.to_json(run, res, cfg), "application/json", "json"
        elif format == "md":
            body, mime, ext = reports.to_markdown(run, res, cfg), "text/markdown", "md"
        elif format == "html":
            body, mime, ext = reports.to_html(run, res, cfg), "text/html", "html"
        else:
            body, mime, ext = reports.to_pytest(run, res, cfg), "text/x-python", "py"
        headers = {"Content-Disposition": f'attachment; filename="authscope-{rid}.{ext}"'} if download else {}
        return Response(body, media_type=f"{mime}; charset=utf-8", headers=headers)

    # -- static frontend (production build) ----------------------------------------------------
    static = Path(os.environ.get("AUTHSCOPE_STATIC", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
    if static.is_dir() and (static / "index.html").exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (static / path).resolve()
            if path and target.is_file() and static.resolve() in target.parents:
                return FileResponse(target)
            if path.startswith("api/"):
                raise HTTPException(404, "not found")
            return FileResponse(static / "index.html")

    return app


app = None  # created lazily by `authscope serve` / uvicorn factory


def factory() -> FastAPI:
    return create_app()
