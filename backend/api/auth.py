from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt


JWKS_CACHE_TTL_SECONDS = 300


def _resolve_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization scheme")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token


@lru_cache(maxsize=8)
def _load_jwks_cached(jwks_url: str, cache_bucket: int) -> dict:
    del cache_bucket  # Cache-buster only; keeps freshest JWKS for each time bucket.
    with urlopen(jwks_url, timeout=5) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _get_cached_jwks(jwks_url: str) -> dict:
    cache_bucket = int(time.time() // JWKS_CACHE_TTL_SECONDS)
    return _load_jwks_cached(jwks_url, cache_bucket)


def _decode_with_hs256(token: str, jwt_secret: str) -> dict:
    return jwt.decode(token, jwt_secret, algorithms=["HS256"], options={"verify_aud": False})


def _decode_with_supabase_jwks(token: str, supabase_url: str, algorithm: str, key_id: str) -> dict:
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        jwks_payload = _get_cached_jwks(jwks_url)
    except (URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch Supabase JWKS for JWT verification",
        ) from exc

    keys = jwks_payload.get("keys")
    if not isinstance(keys, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase JWKS response is malformed",
        )

    key = next((candidate for candidate in keys if candidate.get("kid") == key_id), None)
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT key id")

    return jwt.decode(token, key, algorithms=[algorithm], options={"verify_aud": False})


def _validate_with_supabase_userinfo(token: str, supabase_url: str, anon_key: str) -> dict:
    userinfo_url = f"{supabase_url.rstrip('/')}/auth/v1/user"
    request = Request(
        userinfo_url,
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": anon_key,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = response.read().decode("utf-8")
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT for Supabase user verification",
        ) from exc

    try:
        user_payload = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase user verification response is malformed",
        ) from exc

    user_id = str(user_payload.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT subject is missing")
    return {"sub": user_id}


def require_user(authorization: str | None = Header(default=None)) -> str:
    token = _resolve_bearer_token(authorization)

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid JWT header: {exc}") from exc

    algorithm = str(header.get("alg") or "").upper()
    key_id = str(header.get("kid") or "").strip()

    if not algorithm:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT algorithm is missing")

    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    supabase_url = (os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL") or "").strip()
    supabase_anon_key = (os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY") or "").strip()

    payload: dict | None = None
    try:
        if algorithm.startswith("HS"):
            if not jwt_secret:
                raise JWTError("Missing SUPABASE_JWT_SECRET for HS* token verification")
            payload = _decode_with_hs256(token, jwt_secret)
        else:
            if not supabase_url:
                raise JWTError("Missing SUPABASE_URL for JWKS token verification")
            if not key_id:
                raise JWTError("Missing JWT key id")
            payload = _decode_with_supabase_jwks(token, supabase_url, algorithm, key_id)
    except JWTError as exc:
        if supabase_url and supabase_anon_key:
            payload = _validate_with_supabase_userinfo(token, supabase_url, supabase_anon_key)
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid JWT: {exc}") from exc

    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT payload")
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT subject is missing")
    return user_id


CurrentUser = Depends(require_user)

