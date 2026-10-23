"""SQLite persistence: projects (config without secrets), runs and per-check results."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectConfig
from .models import CheckResult, RunInfo, RunStats

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  status TEXT NOT NULL, modules TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
  error TEXT, stats TEXT NOT NULL, extra TEXT NOT NULL DEFAULT '{}', config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, idx INTEGER NOT NULL,
  id TEXT NOT NULL, module TEXT NOT NULL, endpoint_key TEXT NOT NULL, identity TEXT,
  verdict TEXT NOT NULL, severity TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY (run_id, idx));
CREATE INDEX IF NOT EXISTS results_run ON results(run_id, verdict);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | None = None) -> None:
        path = path or os.environ.get("AUTHSCOPE_DB", "data/authscope.db")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    # -- projects ----------------------------------------------------------------------
    def create_project(self, cfg: ProjectConfig) -> str:
        pid = uuid.uuid4().hex[:10]
        with self._lock, self._db:
            self._db.execute("INSERT INTO projects VALUES (?,?,?,?,?)",
                             (pid, cfg.name, cfg.model_dump_json(), now(), now()))
        return pid

    def update_project(self, pid: str, cfg: ProjectConfig) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE projects SET name=?, config=?, updated_at=? WHERE id=?",
                             (cfg.name, cfg.model_dump_json(), now(), pid))

    def get_project(self, pid: str) -> ProjectConfig | None:
        row = self._db.execute("SELECT config FROM projects WHERE id=?", (pid,)).fetchone()
        return ProjectConfig.model_validate_json(row["config"]) if row else None

    def list_projects(self) -> list[dict]:
        rows = self._db.execute("SELECT id, name, config, updated_at FROM projects ORDER BY updated_at DESC")
        out = []
        for r in rows:
            cfg = json.loads(r["config"])
            out.append({"id": r["id"], "name": r["name"], "base_url": cfg["target"]["base_url"],
                        "endpoints": len(cfg.get("endpoints", [])), "updated_at": r["updated_at"]})
        return out

    def delete_project(self, pid: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM projects WHERE id=?", (pid,))

    # -- runs --------------------------------------------------------------------------
    def create_run(self, project_id: str, modules: list[str], cfg: ProjectConfig) -> RunInfo:
        run = RunInfo(id=uuid.uuid4().hex[:10], project_id=project_id, status="queued",
                      modules=modules, started_at=now())
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO runs (id, project_id, status, modules, started_at, stats, config) "
                "VALUES (?,?,?,?,?,?,?)",
                (run.id, project_id, run.status, json.dumps(modules), run.started_at,
                 run.stats.model_dump_json(), cfg.model_dump_json()))
        return run

    def update_run(self, run: RunInfo) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE runs SET status=?, finished_at=?, error=?, stats=?, extra=? WHERE id=?",
                (run.status, run.finished_at, run.error, run.stats.model_dump_json(),
                 json.dumps(run.extra), run.id))

    @staticmethod
    def _run(row: sqlite3.Row) -> RunInfo:
        return RunInfo(id=row["id"], project_id=row["project_id"], status=row["status"],
                       modules=json.loads(row["modules"]), started_at=row["started_at"],
                       finished_at=row["finished_at"], error=row["error"],
                       stats=RunStats.model_validate_json(row["stats"]), extra=json.loads(row["extra"]))

    def get_run(self, rid: str) -> RunInfo | None:
        row = self._db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        return self._run(row) if row else None

    def run_config(self, rid: str) -> ProjectConfig | None:
        row = self._db.execute("SELECT config FROM runs WHERE id=?", (rid,)).fetchone()
        return ProjectConfig.model_validate_json(row["config"]) if row else None

    def list_runs(self, project_id: str, limit: int = 20) -> list[RunInfo]:
        rows = self._db.execute(
            "SELECT * FROM runs WHERE project_id=? ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (project_id, limit))
        return [self._run(r) for r in rows]

    def latest_run(self, project_id: str, finished_only: bool = True) -> RunInfo | None:
        q = "SELECT * FROM runs WHERE project_id=?" + (" AND status IN ('completed','cancelled')" if finished_only else "")
        row = self._db.execute(q + " ORDER BY started_at DESC, rowid DESC LIMIT 1", (project_id,)).fetchone()
        return self._run(row) if row else None

    def fail_stale_runs(self) -> None:
        """Runs left 'running' by a crashed process can never finish."""
        with self._lock, self._db:
            self._db.execute("UPDATE runs SET status='failed', error='server restarted during run', finished_at=? "
                             "WHERE status IN ('queued','running')", (now(),))

    # -- results -----------------------------------------------------------------------
    def add_result(self, run_id: str, idx: int, r: CheckResult) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?)",
                             (run_id, idx, r.id, r.module, r.endpoint_key, r.identity, r.verdict,
                              r.severity, r.model_dump_json()))

    def results(self, run_id: str, verdicts: list[str] | None = None, module: str | None = None) -> list[CheckResult]:
        q, args = "SELECT data FROM results WHERE run_id=?", [run_id]
        if verdicts:
            q += f" AND verdict IN ({','.join('?' * len(verdicts))})"
            args += verdicts
        if module:
            q += " AND module=?"
            args.append(module)
        return [CheckResult.model_validate_json(r["data"]) for r in self._db.execute(q + " ORDER BY idx", args)]

    def result(self, run_id: str, result_id: str) -> CheckResult | None:
        row = self._db.execute("SELECT data FROM results WHERE run_id=? AND id=?", (run_id, result_id)).fetchone()
        return CheckResult.model_validate_json(row["data"]) if row else None
