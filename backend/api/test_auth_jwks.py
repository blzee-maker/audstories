"""Verification of Supabase tokens signed with asymmetric JWT Signing Keys.

Supabase's current model signs user tokens with an asymmetric key (ES256/RS256)
that the backend verifies against the project's public JWKS endpoint. No shared
secret is involved, which is why SUPABASE_JWT_SECRET is optional.

These tests stub the JWKS fetch with a genuine EC keypair, so the decode path
runs for real rather than dying at the network call.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jose import jwt as jose_jwt

from . import auth

KID = "test-signing-key"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture(scope="module")
def keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "kid": KID,
        "alg": "ES256",
        "use": "sig",
        "x": _b64u(numbers.x.to_bytes(32, "big")),
        "y": _b64u(numbers.y.to_bytes(32, "big")),
    }
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return {"jwk": jwk, "private_pem": private_pem, "public_pem": public_pem}


@pytest.fixture(autouse=True)
def supabase_env(monkeypatch, keypair):
    """Point the verifier at a stubbed JWKS and clear every fallback path."""
    monkeypatch.setattr(auth, "DEV_NO_AUTH", False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    # No shared secret and no anon key: proves the asymmetric path stands alone,
    # with neither the legacy HS256 route nor the userinfo fallback available.
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("VITE_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setattr(auth, "_get_cached_jwks", lambda url: {"keys": [keypair["jwk"]]})


def _unsigned(alg: str, kid: str | None = KID) -> str:
    header = {"alg": alg, "typ": "JWT"}
    if kid:
        header["kid"] = kid
    body = {"sub": "attacker-user-id"}
    return "%s.%s." % (
        _b64u(json.dumps(header).encode()),
        _b64u(json.dumps(body).encode()),
    )


def test_valid_es256_token_is_accepted(keypair):
    token = jose_jwt.encode(
        {"sub": "user-abc"}, keypair["private_pem"], algorithm="ES256", headers={"kid": KID}
    )
    assert auth.require_user(f"Bearer {token}") == "user-abc"


def test_no_shared_secret_is_required(keypair):
    """The whole point of the migration: verification with no secret configured."""
    import os

    assert not os.environ.get("SUPABASE_JWT_SECRET")
    token = jose_jwt.encode(
        {"sub": "user-xyz"}, keypair["private_pem"], algorithm="ES256", headers={"kid": KID}
    )
    assert auth.require_user(f"Bearer {token}") == "user-xyz"


@pytest.mark.parametrize("alg", ["none", "None", "NONE"])
def test_unsigned_token_is_rejected(alg):
    with pytest.raises(HTTPException) as excinfo:
        auth.require_user(f"Bearer {_unsigned(alg)}")
    assert excinfo.value.status_code == 401


def test_unsigned_es256_token_is_rejected():
    """Correct algorithm and a real kid, but no signature."""
    with pytest.raises(HTTPException) as excinfo:
        auth.require_user(f"Bearer {_unsigned('ES256')}")
    assert excinfo.value.status_code == 401


def test_unknown_algorithm_is_rejected():
    """The token's own alg must not be echoed into the permitted-algorithm list."""
    with pytest.raises(HTTPException) as excinfo:
        auth.require_user(f"Bearer {_unsigned('HS512xyz')}")
    assert excinfo.value.status_code == 401


def test_unknown_key_id_is_rejected(keypair):
    token = jose_jwt.encode(
        {"sub": "user-abc"},
        keypair["private_pem"],
        algorithm="ES256",
        headers={"kid": "some-other-key"},
    )
    with pytest.raises(HTTPException) as excinfo:
        auth.require_user(f"Bearer {token}")
    assert excinfo.value.status_code == 401


def test_token_signed_by_a_different_key_is_rejected():
    stranger = ec.generate_private_key(ec.SECP256R1())
    pem = stranger.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    token = jose_jwt.encode({"sub": "attacker"}, pem, algorithm="ES256", headers={"kid": KID})
    with pytest.raises(HTTPException) as excinfo:
        auth.require_user(f"Bearer {token}")
    assert excinfo.value.status_code == 401


def test_token_without_subject_is_rejected(keypair):
    token = jose_jwt.encode(
        {"role": "authenticated"}, keypair["private_pem"], algorithm="ES256", headers={"kid": KID}
    )
    with pytest.raises(HTTPException) as excinfo:
        auth.require_user(f"Bearer {token}")
    assert excinfo.value.status_code == 401
