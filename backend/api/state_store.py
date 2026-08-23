from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class StateStore:
    """SQLite-backed store for project and job state.

    Replaces the previous flat-JSON implementation. On first run, if a
    sibling ``api_state.json`` file exists it is migrated automatically
    and renamed to ``api_state.json.migrated``.

    Thread safety: a single connection is kept open for the lifetime of
    the process. A threading.Lock serialises all reads and writes so the
    store is safe to call from the FastAPI request threads and the
    background worker thread simultaneously.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._migrate_from_json()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id   TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id   TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
                """
            )

    def _migrate_from_json(self) -> None:
        json_path = self.path.with_suffix(".json")
        if not json_path.is_file():
            return
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        with self._lock, self._conn:
            for project_id, data in payload.get("projects", {}).items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO projects (id, data) VALUES (?, ?)",
                    (project_id, json.dumps(data)),
                )
            for job_id, data in payload.get("jobs", {}).items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO jobs (id, data) VALUES (?, ?)",
                    (job_id, json.dumps(data)),
                )

        json_path.rename(json_path.with_suffix(".json.migrated"))

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def create_or_update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                row = self._conn.execute(
                    "SELECT data FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                existing = json.loads(row["data"]) if row else {}
                merged = {**existing, **payload}
                self._conn.execute(
                    "INSERT OR REPLACE INTO projects (id, data) VALUES (?, ?)",
                    (project_id, json.dumps(merged)),
                )
        return merged

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return json.loads(row["data"]) if row else None

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                row = self._conn.execute(
                    "SELECT data FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(project_id)
                data = json.loads(row["data"])
                data.update(fields)
                self._conn.execute(
                    "UPDATE projects SET data = ? WHERE id = ?",
                    (json.dumps(data), project_id),
                )
        return data

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def add_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO jobs (id, data) VALUES (?, ?)",
                (job_id, json.dumps(payload)),
            )
        return payload

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            with self._conn:
                row = self._conn.execute(
                    "SELECT data FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(job_id)
                data = json.loads(row["data"])
                data.update(fields)
                self._conn.execute(
                    "UPDATE jobs SET data = ? WHERE id = ?",
                    (json.dumps(data), job_id),
                )
        return data

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return all persisted job records (used for restart recovery)."""
        with self._lock:
            rows = self._conn.execute("SELECT data FROM jobs").fetchall()
        return [json.loads(row["data"]) for row in rows]
