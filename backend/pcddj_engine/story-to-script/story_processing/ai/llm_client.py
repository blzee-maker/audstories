"""LLM client — abstract interface + concrete implementations.

Provides a swappable LLM backend for controlled AI classification.
All implementations enforce: temperature=0, top_p=1, JSON-only output.

Includes a shared :func:`call_with_backoff` helper for transport-level
retry with exponential backoff, and a :class:`FallbackLLMClient` that
chains a primary → fallback provider.
"""

from __future__ import annotations

import logging
import os
import re
import time
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

# Regex to strip markdown JSON fences the model may wrap around output
_JSON_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL,
)


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` wrapping if present."""
    m = _JSON_FENCE_RE.match(text)
    return m.group(1).strip() if m else text.strip()


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class LLMClient(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def complete(self, prompt: str, *, system: str = "") -> str:
        """Send a prompt and return the raw text response.

        Parameters
        ----------
        prompt:
            The user/classification prompt.
        system:
            Optional system-level instruction.

        Returns
        -------
        str — raw text response from the model.
        """

    def close(self) -> None:
        """Release any held resources (HTTP connections, etc.).

        Default implementation is a no-op.  Override in subclasses that
        hold persistent connections.
        """


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

class QuotaExhaustedError(RuntimeError):
    """Raised when an upstream provider quota is exhausted.

    Retrying will not help until the quota resets or billing changes.
    """


def _is_quota_exhausted_exception(exc: Exception) -> bool:
    """Best-effort detection of quota-exhaustion 429s.

    We intentionally key off the message content because upstream exception
    types differ across SDK versions/endpoints.
    """
    msg = str(exc).lower()
    if "resource_exhausted" not in msg:
        return False
    # Gemini quota-exhaustion messages include things like:
    # - "You exceeded your current quota"
    # - "quota exceeded for metric ... free_tier_requests"
    return (
        "exceeded your current quota" in msg
        or "quota exceeded" in msg
        or "free_tier_requests" in msg
    )


def call_with_backoff(
    client: LLMClient,
    prompt: str,
    *,
    system: str = "",
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> str:
    """Call ``client.complete()`` with exponential backoff on failure.

    Retries transport / API errors only.  JSON-parse failures should be
    handled by the caller's own retry loop.

    Raises the final exception if all retries are exhausted.
    """
    for attempt in range(max_retries):
        try:
            return client.complete(prompt, system=system)
        except Exception as exc:
            if _is_quota_exhausted_exception(exc):
                # Circuit-breaker: don't waste minutes on retries when quota is
                # exhausted for the day/free-tier request budget.
                raise QuotaExhaustedError(
                    "Upstream LLM quota exhausted; failing fast (no retries)."
                ) from exc
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.1fs…",
                attempt + 1,
                max_retries,
                delay,
            )
            time.sleep(delay)
    raise RuntimeError("call_with_backoff: unreachable")


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------

class LocalLLMClient(LLMClient):
    """Ollama-compatible local LLM client (default).

    Calls ``/api/generate`` with ``stream=false``.
    Automatically strips ``<think>`` tags from models that use
    thinking mode (e.g. Qwen3).
    """

    _THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:4b",
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._http = httpx.Client(timeout=self.timeout)

    def complete(self, prompt: str, *, system: str = "") -> str:
        payload: dict = {
            "model": self.model,
            "prompt": f"/no_think\n{prompt}",
            "stream": False,
            "options": {
                "temperature": 0,
                "top_p": 1,
            },
        }
        if system:
            payload["system"] = system

        resp = self._http.post(
            f"{self.base_url}/api/generate", json=payload,
        )
        resp.raise_for_status()

        data = resp.json()
        raw = data.get("response", "")

        raw = self._THINK_RE.sub("", raw).strip()
        return raw

    def close(self) -> None:
        self._http.close()


class OpenAIClient(LLMClient):
    """OpenAI-compatible client (works with OpenAI API or any compatible
    endpoint such as vLLM, LM Studio, etc.).

    Calls ``/v1/chat/completions`` with JSON mode.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._http = httpx.Client(timeout=self.timeout)

    def complete(self, prompt: str, *, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "top_p": 1,
            "response_format": {"type": "json_object"},
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = self._http.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def close(self) -> None:
        self._http.close()


class GeminiClient(LLMClient):
    """Google Gemini API client via the ``google-genai`` SDK.

    Uses ``response_mime_type="application/json"`` for structured output,
    ``temperature=0``, and ``top_p=1`` for deterministic responses.

    Forces the ``v1alpha`` API version to avoid the known SDK bug where
    ``systemInstruction`` and ``responseMimeType`` are rejected by the
    ``v1`` endpoint (googleapis/python-genai#425).
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.0-flash",
        timeout: int = 60_000,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Pass api_key= or set GEMINI_API_KEY env var."
            )
        self.model = model

        from google import genai  # noqa: E402 — lazy import
        from google.genai import types as genai_types  # noqa: E402

        self._client = genai.Client(
            api_key=self.api_key,
            http_options=genai_types.HttpOptions(
                api_version="v1alpha",
                timeout=timeout,
            ),
        )

    def complete(self, prompt: str, *, system: str = "") -> str:
        from google.genai import types  # noqa: E402 — lazy import

        config = types.GenerateContentConfig(
            temperature=0,
            top_p=1,
            response_mime_type="application/json",
            system_instruction=system or None,
        )

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        raw = response.text or ""
        return _strip_json_fences(raw)


# ---------------------------------------------------------------------------
# Fallback wrapper
# ---------------------------------------------------------------------------

class FallbackLLMClient(LLMClient):
    """Wraps a *primary* and *fallback* client.

    If the primary raises on ``.complete()``, the fallback is tried once.
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        self.primary = primary
        self.fallback = fallback

    def complete(self, prompt: str, *, system: str = "") -> str:
        try:
            return self.primary.complete(prompt, system=system)
        except Exception:
            logger.warning(
                "Primary LLM (%s) failed, falling back to %s",
                type(self.primary).__name__,
                type(self.fallback).__name__,
            )
            return self.fallback.complete(prompt, system=system)

    def close(self) -> None:
        self.primary.close()
        self.fallback.close()
