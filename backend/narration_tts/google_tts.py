"""Synthesize narrator audio via Gemini Flash TTS (google-genai, audio modality)."""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import struct
import time
from pathlib import Path
import wave

from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.contracts.requirements_models import TrackType
from asset_engine.requirements.extractor import extract_requirements

from narration_tts.folder_paths import voice_clip_asset_dir

logger = logging.getLogger(__name__)

# Long chapters: split text; each sub-chunk is streamed then WAVs are concatenated.
_MAX_SYNTH_CHARS = 4500


def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
    """Parse bits per sample and sample rate from an audio MIME type string."""
    bits_per_sample = 16
    rate = 24000

    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate_str = param.split("=", 1)[1]
                rate = int(rate_str)
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass

    return {"bits_per_sample": bits_per_sample, "rate": rate}


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Wrap raw PCM *audio_data* in a WAV container using *mime_type* hints."""
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = int(parameters["bits_per_sample"] or 16)
    sample_rate = int(parameters["rate"] or 24000)
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def _inline_data_to_wav_bytes(data: bytes, mime_type: str) -> bytes:
    """Normalize inline API audio to a full WAV byte string."""
    ext = mimetypes.guess_extension(mime_type or "")
    if ext == ".wav":
        return data
    if ext is None:
        return convert_to_wav(data, mime_type)
    return convert_to_wav(data, mime_type)


def _concat_wav_byte_strings(wav_parts: list[bytes]) -> bytes:
    """Concatenate WAV payloads by joining PCM frames (same format required)."""
    if not wav_parts:
        raise ValueError("No audio data to concatenate.")
    if len(wav_parts) == 1:
        return wav_parts[0]

    frames_chunks: list[bytes] = []
    params: tuple[int, int, int] | None = None

    for wb in wav_parts:
        with wave.open(io.BytesIO(wb), "rb") as w_in:
            p = (w_in.getnchannels(), w_in.getsampwidth(), w_in.getframerate())
            if params is None:
                params = p
            elif p != params:
                raise RuntimeError(
                    f"Gemini TTS returned mismatched audio params: {p} vs {params}",
                )
            frames_chunks.append(w_in.readframes(w_in.getnframes()))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w_out:
        w_out.setnchannels(params[0])  # type: ignore[union-attr]
        w_out.setsampwidth(params[1])
        w_out.setframerate(params[2])
        w_out.writeframes(b"".join(frames_chunks))
    return buf.getvalue()


def _api_key(explicit: str | None = None) -> str:
    key = (explicit or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "Set GEMINI_API_KEY (same key as story-to-script / AI Studio) "
            "for Gemini Flash TTS.",
        )
    return key


def _tts_model() -> str:
    # Default is a known-valid Gemini TTS model id (Google's convention is
    # "gemini-<ver>-<tier>-preview-tts"). Override with GEMINI_TTS_MODEL to use a
    # newer TTS model without a code change. List valid ids for your key with:
    #   python -m narration_tts.list_tts_models
    return os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()


def _tts_voice() -> str:
    return os.environ.get("GEMINI_TTS_VOICE", "Algieba").strip() or "Algieba"


def _tts_temperature() -> float:
    raw = os.environ.get("GEMINI_TTS_TEMPERATURE", "1")
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _split_text_for_synthesis(text: str, max_chars: int = _MAX_SYNTH_CHARS) -> list[str]:
    """Split long text into API-sized chunks (word-aware). Output is still one WAV."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            cut = text.rfind(" ", start + max_chars // 2, end)
            if cut == -1 or cut <= start:
                cut = end
            else:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end if end > start else start + max_chars
    return chunks


def _stream_one_chunk_to_wav_list(
    text: str,
    *,
    api_key: str,
    max_retries: int = 4,
) -> bytes:
    """Run Gemini Flash TTS on *text*; return one WAV byte string."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'google-genai'. Install with: "
            "python -m pip install -r narration_tts/requirements.txt "
            "(or pip install google-genai).",
        ) from exc

    client = genai.Client(api_key=api_key)
    model = _tts_model()
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=text)],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=_tts_temperature(),
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=_tts_voice(),
                ),
            ),
        ),
    )

    wav_segments: list[bytes] = []
    delay = 1.0
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            stream = client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            )
            for chunk in stream:
                if chunk.parts is None:
                    continue
                part0 = chunk.parts[0]
                if part0.inline_data and part0.inline_data.data:
                    inline = part0.inline_data
                    mime = inline.mime_type or "audio/L16;rate=24000"
                    wav_segments.append(
                        _inline_data_to_wav_bytes(inline.data, mime),
                    )
                elif getattr(chunk, "text", None):
                    logger.debug("Gemini TTS text chunk: %s", chunk.text[:200])

            if wav_segments:
                return _concat_wav_byte_strings(wav_segments)

            raise RuntimeError("Gemini TTS stream produced no audio parts.")

        except Exception as exc:
            last_err = exc
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            retriable = code in (429, 500, 502, 503) if isinstance(code, int) else True
            if retriable and attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                wav_segments.clear()
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError("Gemini TTS failed after retries")


def synthesize_text_to_linear16_wav(
    text: str,
    out_wav: Path,
    *,
    api_key: str | None = None,
    sample_rate_hertz: int = 24000,
    max_retries: int = 4,
) -> None:
    """Synthesize *text* to a **single** WAV via Gemini Flash TTS (chunks merged if long).

    *sample_rate_hertz* is accepted for API compatibility; output rate follows the API.
    """
    del sample_rate_hertz  # Gemini TTS defines rate via MIME / WAV
    key = _api_key(api_key)
    parts = _split_text_for_synthesis(text)
    if not parts:
        raise ValueError("No text to synthesize.")

    wav_parts: list[bytes] = []
    for part in parts:
        wav_parts.append(_stream_one_chunk_to_wav_list(part, api_key=key, max_retries=max_retries))

    final_wav = _concat_wav_byte_strings(wav_parts)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    out_wav.write_bytes(final_wav)


def fill_voice_requirements_from_draft(
    draft_path: Path,
    library_root: Path,
    *,
    skip_existing: bool = True,
) -> int:
    """Generate WAVs for every voice requirement under *library_root*.

    Returns the number of clips synthesized (skipped clips do not count).
    """
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    draft = DraftTimeline(**payload)
    reqs = extract_requirements(draft)
    voice_reqs = [r for r in reqs if r.track_type == TrackType.VOICE]
    if not voice_reqs:
        return 0

    key = _api_key()
    done = 0
    for req in voice_reqs:
        text = (req.tts_text or req.descriptor or "").strip()
        if not text:
            continue
        folder = voice_clip_asset_dir(library_root, req)
        folder.mkdir(parents=True, exist_ok=True)
        out_wav = folder / "narration_tts.wav"
        if skip_existing and out_wav.is_file() and out_wav.stat().st_size > 0:
            continue
        synthesize_text_to_linear16_wav(text, out_wav, api_key=key)
        done += 1
    return done
