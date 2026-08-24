"""Tests for the AS_DEV_NO_AUTH development bypass.

The bypass disables authentication entirely, so the guard around it matters more
than the feature. These tests pin both halves: that it works when asked for
locally, and that it refuses to activate when the process looks remote-facing.
"""

from __future__ import annotations

import importlib

import pytest


def _reload_config(monkeypatch, *, flag: str | None, cors: str | None):
    """Re-import api.config with a specific environment.

    DEV_NO_AUTH is evaluated at import time (so misconfiguration fails at
    startup), which means changing it requires reloading the module.
    """
    if flag is None:
        monkeypatch.delenv("AS_DEV_NO_AUTH", raising=False)
    else:
        monkeypatch.setenv("AS_DEV_NO_AUTH", flag)
    if cors is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", cors)

    import api.config

    return importlib.reload(api.config)


@pytest.fixture(autouse=True)
def _restore_config():
    """Leave api.config (and anything importing from it) as we found it."""
    yield
    import api.auth
    import api.config

    importlib.reload(api.config)
    importlib.reload(api.auth)


def test_disabled_by_default(monkeypatch):
    config = _reload_config(monkeypatch, flag=None, cors=None)
    assert config.DEV_NO_AUTH is False


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_enabled_by_truthy_values_when_origins_are_local(monkeypatch, flag):
    config = _reload_config(monkeypatch, flag=flag, cors="http://localhost:5173")
    assert config.DEV_NO_AUTH is True


@pytest.mark.parametrize("flag", ["0", "false", "no", "", "maybe"])
def test_ignored_for_non_truthy_values(monkeypatch, flag):
    config = _reload_config(monkeypatch, flag=flag, cors="http://localhost:5173")
    assert config.DEV_NO_AUTH is False


def test_defaults_to_local_origins_when_cors_unset(monkeypatch):
    # No CORS_ORIGINS means the built-in localhost defaults, which are safe.
    config = _reload_config(monkeypatch, flag="1", cors=None)
    assert config.DEV_NO_AUTH is True


@pytest.mark.parametrize(
    "cors",
    [
        "https://audstories.example.com",
        "http://localhost:5173,https://audstories.example.com",
        "http://192.168.1.50:5173",
    ],
)
def test_refuses_to_activate_for_remote_origins(monkeypatch, cors):
    """The whole point of the guard: never bypass auth for a remote-facing process."""
    with pytest.raises(RuntimeError, match="AS_DEV_NO_AUTH"):
        _reload_config(monkeypatch, flag="1", cors=cors)


def test_loopback_variants_are_treated_as_local(monkeypatch):
    config = _reload_config(
        monkeypatch,
        flag="1",
        cors="http://127.0.0.1:5173,http://localhost:5174,http://0.0.0.0:8000",
    )
    assert config.DEV_NO_AUTH is True


def test_require_user_returns_dev_user_without_a_token(monkeypatch):
    _reload_config(monkeypatch, flag="1", cors="http://localhost:5173")
    import api.auth

    auth = importlib.reload(api.auth)
    assert auth.require_user(authorization=None) == "dev-local-user"


def test_require_user_still_rejects_when_bypass_is_off(monkeypatch):
    from fastapi import HTTPException

    _reload_config(monkeypatch, flag=None, cors="http://localhost:5173")
    import api.auth

    auth = importlib.reload(api.auth)
    with pytest.raises(HTTPException) as exc:
        auth.require_user(authorization=None)
    assert exc.value.status_code == 401
