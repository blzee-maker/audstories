"""spaCy pipeline — singleton model loader and Doc processing."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import spacy

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.tokens import Doc

# ---------------------------------------------------------------------------
# Singleton model cache
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_models: dict[str, Language] = {}


def _load_model(name: str = "en_core_web_lg") -> Language:
    """Load a spaCy model once and cache it for reuse.

    Thread-safe via a module-level lock.
    """
    if name not in _models:
        with _lock:
            # Double-check after acquiring lock
            if name not in _models:
                _models[name] = spacy.load(name)
    return _models[name]


def run_spacy(text: str, *, model_name: str = "en_core_web_lg") -> Doc:
    """Run the full spaCy pipeline on *text* and return a ``Doc``.

    Parameters
    ----------
    text:
        Normalized story text.
    model_name:
        spaCy model to use. Change to ``"en_core_web_trf"`` for
        transformer-grade accuracy (requires PyTorch).

    Returns
    -------
    spacy.tokens.Doc
    """
    nlp = _load_model(model_name)
    return nlp(text)
