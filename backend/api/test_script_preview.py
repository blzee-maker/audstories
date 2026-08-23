from __future__ import annotations

from fastapi.testclient import TestClient

from .auth import require_user
from .main import app, store


def _fake_user() -> str:
    return "test-user"


def test_script_preview_endpoint_is_side_effect_free():
    app.dependency_overrides[require_user] = _fake_user
    try:
        project_id = "preview-test-project"
        store.create_or_update_project(
            project_id,
            {
                "id": project_id,
                "unit_id": "u1",
                "name": "Preview Test",
                "active_unit_name": "Episode 1",
                "active_unit_slug": "u1",
                "format": "drama",
                "status": "queued",
                "user_id": "test-user",
                "story_text": "SCENE ONE\nINT. ROOM\nEVA\nHello there.",
            },
        )
        client = TestClient(app)
        res = client.post(f"/api/projects/{project_id}/script/preview", json={})
        assert res.status_code == 200, res.text
        payload = res.json()
        assert payload["project_id"] == project_id
        assert isinstance(payload["diagnostics"], list)
        assert len(payload["scenes"]) >= 1
    finally:
        app.dependency_overrides.clear()
