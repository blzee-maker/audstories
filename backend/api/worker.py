from __future__ import annotations

import queue
import re
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .state_store import StateStore

_PATH_PATTERN = re.compile(r'[A-Za-z]:\\[^\s"\']+|/(?:home|usr|var|tmp|workspace|app)/[^\s"\']*')


def _safe_error(exc: Exception) -> str:
    """Return a client-safe error string with filesystem paths redacted."""
    msg = str(exc)
    msg = _PATH_PATTERN.sub("[path redacted]", msg)
    return msg[:400]


@dataclass
class JobPayload:
    job_id: str
    project_id: str
    action: str
    unit_slug: str
    previous_status: str | None = None


class PipelineWorker:
    def __init__(self, *, repo_root: Path, state_store: StateStore) -> None:
        self.repo_root = repo_root
        self.state_store = state_store
        self.projects_root = self.repo_root / "workspace"
        self._queue: queue.Queue[JobPayload] = queue.Queue()
        self._recover_jobs()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _recover_jobs(self) -> None:
        """Reconcile persisted jobs after a restart.

        ``queued`` jobs never started, so they are safely re-enqueued from
        the top. ``running`` jobs were interrupted mid-subprocess; re-running
        could duplicate partial work, so they are marked failed and the user
        is asked to retry. This prevents projects being stranded in a
        non-terminal status forever after a crash or restart.
        """
        try:
            jobs = self.state_store.list_jobs()
        except Exception:  # noqa: BLE001 — never let recovery block startup
            return

        for job in jobs:
            job_id = job.get("id")
            project_id = job.get("project_id")
            status = job.get("status")
            if not job_id or not project_id:
                continue
            try:
                if status == "queued":
                    project = self.state_store.get_project(project_id)
                    if project is None:
                        continue
                    self._queue.put(
                        JobPayload(
                            job_id=job_id,
                            project_id=project_id,
                            action=str(job.get("action", "")),
                            unit_slug=str(project.get("active_unit_slug", "")),
                            previous_status=job.get("previous_status"),
                        )
                    )
                elif status == "running":
                    msg = "Interrupted by a server restart. Please retry."
                    self.state_store.update_job(job_id, status="failed", error=msg)
                    if self.state_store.get_project(project_id) is not None:
                        self.state_store.update_project(
                            project_id, status="failed", error=msg
                        )
            except Exception:  # noqa: BLE001 — one bad job must not abort recovery
                continue

    def enqueue(self, *, project_id: str, action: str, unit_slug: str) -> str:
        job_id = str(uuid.uuid4())
        project = self.state_store.get_project(project_id) or {}
        previous_status = project.get("status")
        self.state_store.add_job(
            job_id,
            {
                "id": job_id,
                "project_id": project_id,
                "action": action,
                "status": "queued",
                "error": None,
                "previous_status": previous_status,
            },
        )
        self.state_store.update_project(project_id, status="queued", active_job_id=job_id, error=None)
        self._queue.put(
            JobPayload(
                job_id=job_id,
                project_id=project_id,
                action=action,
                unit_slug=unit_slug,
                previous_status=previous_status,
            )
        )
        return job_id

    def _call(self, args: list[str]) -> None:
        result = subprocess.run(args, cwd=str(self.repo_root), capture_output=True, text=True)
        if result.returncode != 0:
            raw_error = (result.stderr or result.stdout or "pipeline failed").strip()
            lowered = raw_error.lower()
            if "resource_exhausted" in lowered or "quota" in lowered:
                raise RuntimeError(
                    "AI TTS quota exhausted. Switching to manual-voice workflow is recommended for now."
                )
            raise RuntimeError(raw_error)

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                self.state_store.update_job(job.job_id, status="running")
                if job.action == "stage1":
                    self.state_store.update_project(job.project_id, status="stage1")
                    self._call(
                        [
                            "python",
                            "book_cli.py",
                            "--projects-root",
                            str(self.projects_root),
                            "stage1",
                            "--project-id",
                            job.project_id,
                            "--chapter",
                            job.unit_slug,
                        ]
                    )
                    project = self.state_store.get_project(job.project_id) or {}
                    narration = str(project.get("narration_choice", "self"))
                    fmt = str(project.get("format", "drama"))
                    if narration == "ai" and fmt == "book":
                        self.state_store.update_project(job.project_id, status="stage2")
                        self._call(
                            [
                                "python",
                                "book_cli.py",
                                "--projects-root",
                                str(self.projects_root),
                                "synthesize",
                                "--project-id",
                                job.project_id,
                                "--force",
                            ]
                        )
                        self._call(
                            [
                                "python",
                                "book_cli.py",
                                "--projects-root",
                                str(self.projects_root),
                                "resume",
                                "--project-id",
                                job.project_id,
                            ]
                        )
                        self.state_store.update_project(job.project_id, status="done")
                    else:
                        self.state_store.update_project(job.project_id, status="awaiting_assets")
                elif job.action == "stage2":
                    self.state_store.update_project(job.project_id, status="stage2")
                    project = self.state_store.get_project(job.project_id) or {}
                    narration = str(project.get("narration_choice", "self"))
                    fmt = str(project.get("format", "drama"))
                    if narration == "ai" and fmt == "book":
                        self._call(
                            [
                                "python",
                                "book_cli.py",
                                "--projects-root",
                                str(self.projects_root),
                                "synthesize",
                                "--project-id",
                                job.project_id,
                                "--force",
                            ]
                        )
                    self._call(
                        [
                            "python",
                            "book_cli.py",
                            "--projects-root",
                            str(self.projects_root),
                            "resume",
                            "--project-id",
                            job.project_id,
                        ]
                    )
                    self.state_store.update_project(job.project_id, status="done")
                elif job.action == "credits":
                    self.state_store.update_project(job.project_id, status="credits")
                    self._call(
                        [
                            "python",
                            "book_cli.py",
                            "--projects-root",
                            str(self.projects_root),
                            "credits",
                            "--project-id",
                            job.project_id,
                        ]
                    )
                    resume_status = job.previous_status or "done"
                    if resume_status not in {"queued", "stage1", "awaiting_assets", "stage2", "credits", "done", "failed"}:
                        resume_status = "done"
                    self.state_store.update_project(job.project_id, status=resume_status)
                self.state_store.update_job(job.job_id, status="done", error=None)
            except Exception as exc:  # noqa: BLE001
                safe_error = _safe_error(exc)
                self.state_store.update_job(job.job_id, status="failed", error=safe_error)
                self.state_store.update_project(job.project_id, status="failed", error=safe_error)
            finally:
                self._queue.task_done()

