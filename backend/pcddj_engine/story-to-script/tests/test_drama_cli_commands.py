"""Smoke tests for drama_cli ergonomics commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _drama_cli() -> Path:
    return _repo_root() / "drama_cli.py"


@pytest.mark.slow
def test_chapter_management_and_dry_run_parse(tmp_path: Path):
    projects_root = tmp_path / "workspace" / "projects"
    base_cmd = [sys.executable, str(_drama_cli()), "--projects-root", str(projects_root)]

    init_input = "Test Drama\nWriter One\nPilot\n"
    init = subprocess.run(
        base_cmd + ["init", "--template"],
        input=init_input,
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert init.returncode == 0, f"{init.stdout}\n{init.stderr}"

    project_id = "Test_Drama"
    project_root = projects_root / project_id
    assert (project_root / "book_metadata.json").is_file()

    add_input = "Episode Two\n\nSCENE ONE\nINT. GARAGE - NIGHT\nEVA\nHello.\nEND\n"
    add = subprocess.run(
        base_cmd + ["add-chapter", "--project-id", project_id],
        input=add_input,
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert add.returncode == 0, f"{add.stdout}\n{add.stderr}"

    listed = subprocess.run(
        base_cmd + ["list-chapters", "--project-id", project_id],
        text=True,
        capture_output=True,
        timeout=60,
        cwd=str(_repo_root()),
    )
    assert listed.returncode == 0, f"{listed.stdout}\n{listed.stderr}"
    assert "episode_two" in listed.stdout

    set_active = subprocess.run(
        base_cmd + ["set-chapter", "--project-id", project_id, "--chapter", "pilot"],
        text=True,
        capture_output=True,
        timeout=60,
        cwd=str(_repo_root()),
    )
    assert set_active.returncode == 0, f"{set_active.stdout}\n{set_active.stderr}"

    preview = subprocess.run(
        base_cmd + ["dry-run-parse", "--project-id", project_id, "--json"],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert preview.returncode == 0, f"{preview.stdout}\n{preview.stderr}"
    payload = json.loads(preview.stdout)
    assert payload["scene_count"] >= 1
    assert "scenes" in payload


@pytest.mark.slow
def test_dry_run_parse_unknown_chapter_fails(tmp_path: Path):
    projects_root = tmp_path / "workspace" / "projects"
    base_cmd = [sys.executable, str(_drama_cli()), "--projects-root", str(projects_root)]
    init_input = "Sample\nWriter\nPilot\n"
    init = subprocess.run(
        base_cmd + ["init", "--template"],
        input=init_input,
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert init.returncode == 0
    project_id = "Sample"
    bad = subprocess.run(
        base_cmd + ["dry-run-parse", "--project-id", project_id, "--chapter", "missing_slug"],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert bad.returncode != 0
    assert "unknown chapter slug" in bad.stderr


@pytest.mark.slow
def test_gita_commands_init_show_update(tmp_path: Path):
    projects_root = tmp_path / "workspace" / "projects"
    base_cmd = [sys.executable, str(_drama_cli()), "--projects-root", str(projects_root)]
    init_input = "Series One\nWriter\nPilot\n"
    init = subprocess.run(
        base_cmd + ["init", "--template"],
        input=init_input,
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert init.returncode == 0, f"{init.stdout}\n{init.stderr}"
    project_id = "Series_One"

    gita_init = subprocess.run(
        base_cmd + ["gita-init", "--project-id", project_id],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert gita_init.returncode == 0, f"{gita_init.stdout}\n{gita_init.stderr}"

    gita_show = subprocess.run(
        base_cmd + ["gita-show", "--project-id", project_id, "--json"],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert gita_show.returncode == 0, f"{gita_show.stdout}\n{gita_show.stderr}"
    payload = json.loads(gita_show.stdout)
    assert payload["project_id"] == project_id

    gita_update = subprocess.run(
        base_cmd + ["gita-update", "--project-id", project_id],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert gita_update.returncode == 0, f"{gita_update.stdout}\n{gita_update.stderr}"

    gita_show_after = subprocess.run(
        base_cmd + ["gita-show", "--project-id", project_id, "--json"],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=str(_repo_root()),
    )
    assert gita_show_after.returncode == 0
    payload_after = json.loads(gita_show_after.stdout)
    assert isinstance(payload_after.get("episodes"), list)
