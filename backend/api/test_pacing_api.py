from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from .auth import require_user
from .main import PROJECTS_ROOT, app, store


def _fake_user() -> str:
    return "test-user"


def test_pacing_get_post_round_trip(tmp_path: Path):
    app.dependency_overrides[require_user] = _fake_user
    project_id = "pacing-test-project"
    project_root = PROJECTS_ROOT / project_id
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    draft = {
        "project": {"name": "demo", "sample_rate": 48000, "bit_depth": 16},
        "settings": {"default_silence": 0.5},
        "tracks": [{"id": "narrator", "type": "voice", "role": "voice"}],
        "scenes": [
            {
                "id": "scene_1",
                "name": "Scene 1",
                "energy": 0.2,
                "tracks": {"narrator": [{"tts_text": "hello", "order": 0}]},
            }
        ],
    }
    (output_dir / "draft_timeline.json").write_text(json.dumps(draft), encoding="utf-8")

    store.create_or_update_project(
        project_id,
        {
            "id": project_id,
            "unit_id": "u1",
            "name": "Pacing Test",
            "active_unit_name": "Episode 1",
            "active_unit_slug": "u1",
            "format": "drama",
            "status": "awaiting_assets",
            "user_id": "test-user",
            "story_text": "",
        },
    )

    client = TestClient(app)
    get_res = client.get(f"/api/projects/{project_id}/pacing")
    assert get_res.status_code == 200
    payload = get_res.json()
    assert payload["project_id"] == project_id
    assert len(payload["scenes"]) == 1

    req_id = payload["scenes"][0]["clips"][0]["requirement_id"]
    post_res = client.post(
        f"/api/projects/{project_id}/pacing",
        json={"clips": {req_id: {"pre_silence_s": 0.4, "post_silence_s": 2.5}}},
    )
    assert post_res.status_code == 200

    overrides_path = output_dir / "pacing_overrides.json"
    saved = json.loads(overrides_path.read_text(encoding="utf-8"))
    assert saved["clips"][req_id]["pre_silence_s"] == 0.4
    assert saved["clips"][req_id]["post_silence_s"] == 2.5

    app.dependency_overrides.clear()
