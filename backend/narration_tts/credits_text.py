"""Build opening / ending credit scripts from ``book_metadata`` templates or overrides."""

from __future__ import annotations


OPENING_TEMPLATE = """AudStories presents
"{book_title}"
Written by {writer_name}
An AI-narrated experience powered by {provider}"""

CLOSING_TEMPLATE = """You've just experienced
"{book_title}"
Written by {writer_name}
Narrated by {voice_name}
An AudStories production
Thank you for listening."""


def _credits_dict(meta: dict) -> dict:
    c = meta.get("credits")
    return c if isinstance(c, dict) else {}


def provider_display_line(meta: dict) -> str:
    """Line for 'powered by …' — explicit ``provider_line`` or ``tts_provider`` mapping."""
    cr = _credits_dict(meta)
    line = str(cr.get("provider_line", "")).strip()
    if line:
        return line
    p = str(cr.get("tts_provider", "google")).strip().lower()
    if p in ("elevenlabs", "eleven"):
        return "ElevenLabs"
    return "Google AI"


def opening_credits_text(meta: dict) -> str:
    """Full opening script: ``credits.opening_text`` override or default template."""
    cr = _credits_dict(meta)
    raw = cr.get("opening_text")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    book = str(meta.get("book_title", "Untitled")).strip() or "Untitled"
    writer = str(meta.get("writer_name", "Unknown")).strip() or "Unknown"
    prov = provider_display_line(meta)
    return OPENING_TEMPLATE.format(book_title=book, writer_name=writer, provider=prov)


def closing_credits_text(meta: dict) -> str:
    """Full closing script: ``credits.closing_text`` override or default template."""
    cr = _credits_dict(meta)
    raw = cr.get("closing_text")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    book = str(meta.get("book_title", "Untitled")).strip() or "Untitled"
    writer = str(meta.get("writer_name", "Unknown")).strip() or "Unknown"
    voice = str(cr.get("voice_name", "AI Narrator")).strip() or "AI Narrator"
    return CLOSING_TEMPLATE.format(book_title=book, writer_name=writer, voice_name=voice)


def ensure_credits_defaults(meta: dict) -> None:
    """Ensure ``credits`` subdict exists for audiobook projects (mutates *meta*)."""
    if str(meta.get("project_type", "")).lower() != "audiobook":
        return
    cr = meta.get("credits")
    if not isinstance(cr, dict):
        meta["credits"] = {}
        cr = meta["credits"]
    cr.setdefault("voice_name", "AI Narrator")
    cr.setdefault("tts_provider", "google")
