# Story-to-Script Engine — Analysis

A comprehensive review of the current capabilities, drawbacks, mitigation strategies, and improvement opportunities.

> **Last updated:** 2026-02-20

---

## Changes Since Previous Analysis

| Area | What Changed |
|------|-------------|
| **Emotion Model** | Replaced 6-anchor cosine-similarity approach with GoEmotions classifier (`SamLowe/roberta-base-go_emotions`) + weighted category mapping to 12 emotions. |
| **Emotion Categories** | Expanded from 6 (anxiety, joy, sadness, anger, calm, neutral) → 12 (+surprise, disgust, love, anticipation, nostalgia, confusion). |
| **Emotion Arc** | Added sub-scene emotion arc with paragraph/sliding-window chunking, batched inference, and EMA + peak-gating + min-segment stabilization. |
| **Scene Segmentation** | Overhauled from simple pattern matching → multi-signal scored system: explicit markers, format-aware whitespace (indent vs. block detection), expanded temporal patterns, spaCy DATE/TIME NER, and paragraph-level semantic-shift detection. Each signal contributes a weighted score; break fires when cumulative score ≥ threshold. |
| **Dialogue Extraction** | Added indirect/reported speech extraction via spaCy `ccomp` dependency parse. Added containment-aware overlap resolver that prefers longer matches. Added `merge_dialogue()` to combine direct + indirect turns. |
| **Speaker Resolution** | Added backward mention-chain scan (up to 3 sentences back) for cross-sentence pronoun → PROPN resolution (PERSON-entity preferred). |
| **Cross-Scene Context** | New `StoryContext` + `StoryContextBuilder` system: rolling emotion/pacing trends, emotion momentum (with guardrails), energy adjustment based on position/trend, speaker continuity tracking. |
| **Speaker Reconciliation** | New `reconcile_speakers()` post-processing pass: global named-speaker registry, proximity-based unknown→named replacement, global unknown renumbering. |
| **Deterministic Scene IDs** | Scene IDs now use content-based SHA-256 hash (`scene_000_a1b2c3d4`) instead of random UUIDs. |
| **Structure Metrics** | Added action verb density metric (70+ high-energy verb lemmas). |
| **Heuristic Fallback** | Overhauled: configurable `HeuristicConfig` dataclass with genre presets (`THRILLER_CONFIG`, `LITERARY_CONFIG`). Multi-signal weighted energy formula (punctuation + variance + action verbs + arousal + pacing). Weighted composite action score replacing single-signal threshold. Continuous confidence scoring formula replacing 3-tier buckets. Context-aware momentum and energy adjustments. |
| **Classification** | Added context-aware LLM prompts with summary-level story context (Guardrail 4). Heuristic fallback also receives context. |
| **Validation Schema** | Expanded Pydantic schema: 12-emotion `EmotionType`, `EmotionArcEntry`, `QuoteStyleType` with `"indirect"`, SFX/ambience/narration-segment sub-models, `action_verb_density` in `SceneSignals`. |
| **DSL Compiler** | Added `DraftTimeline` Pydantic validation (`dsl/validator.py`): track purity, track existence, order continuity, gain clamping, EQ preset validation. Indirect speech clips routed to narrator track. |
| **DSL Schema** | Full Pydantic v2 models for Draft Timeline: `DraftTimeline`, `DraftScene`, `DraftClip`, `DraftTrack`, `ProjectConfig`, `DraftSettings`, `DuckingConfig`, `DuckingRule`, `DialogueCompression`, `SceneCrossfade`, `LoudnessConfig`, `SceneRules`, `SceneEQRules`, `SceneDuckingOverride`. |
| **CLI** | Full `argparse`-based CLI (`audstories`) with `process` (single file) and `batch` (directory) subcommands. Model auto-detection by name prefix. `--no-llm` flag. Registered as console script via `pyproject.toml`. |
| **Testing** | Comprehensive test suite added: 18 test files covering normalizer, segmenter, dialogue extractor, speaker resolver, structure metrics, classifier, fallback rules, context, narrative plan, compiler, DSL builders, DSL constants, DSL validator, story validation, pipeline contract, CLI smoke, and determinism. Session-scoped spaCy fixture with `en_core_web_sm`. `MockLLMClient` for unit tests. |
| **Packaging** | `pyproject.toml` with `setuptools` backend, `audstories` console script entry point, test optional dependencies, pytest markers (`slow`, `spacy`, `contract`). |

---

## 1. Current Abilities

### 1.1 Text Preprocessing (`story_processing/preprocessing/normalizer.py`)
- Unicode NFKC normalization for consistent character representation.
- Smart/curly quote → straight quote conversion (covers 10 different Unicode quote characters).
- Control character stripping (preserves `\n`, `\r`, `\t`).
- Inline whitespace collapsing (spaces/tabs → single space, newlines preserved).
- Excessive blank line collapsing (4+ newlines → 3, preserving both paragraph breaks and major structural breaks).

### 1.2 Scene Segmentation (`story_processing/nlp/scene_segmenter.py`)
- **Multi-signal scored architecture**: each boundary candidate accumulates weighted scores from multiple detection layers; a break fires when the cumulative score meets a configurable threshold (default 0.55).
- **Layer 1 — Explicit markers** (score 1.0): `Chapter`, `Scene`, `Act`, `Part` (with Roman/Arabic numerals), `---`, `===`, `***`.
- **Layer 2 — Format-aware whitespace** (score 0.75–0.85):
  - Auto-detects text format: **Normal Indent** (tab-indented paragraphs, blank line = scene break) vs. **Block** (web-style paragraphs, triple newline = break) vs. **unknown**.
  - Triple-newline structural break detection (score 0.75, all formats).
  - Double-newline break detection (score 0.85, indent format only).
- **Layer 3a — Temporal patterns** (score 0.65): 50+ regex patterns covering original patterns, numeric time skips ("three years passed"), sleep/waking transitions, event-based transitions ("after the funeral"), seasonal/temporal shifts ("it was winter now"), and generic time-skip openers ("time marched on").
- **Layer 3b — spaCy NER** (score 0.40): DATE/TIME entities at sentence starts contribute additional break evidence.
- **Layer 4 — Semantic shift detection** (score 0.55): paragraph-level embedding similarity using `all-MiniLM-L6-v2`; breaks where cosine distance > threshold (default 0.35).
- Graceful fallback: treats entire text as a single scene when no breaks exceed the threshold.

### 1.3 Dialogue Extraction (`story_processing/nlp/dialogue_extractor.py`)
- **Direct speech** (regex-based):
  - Three quote styles detected: double-quoted (`"…"`), single-quoted (`'…'`), and em-dash dialogue (`— …`).
  - Single-quote regex guards against false positives from apostrophes (minimum 2 characters, whitespace boundaries).
- **Indirect speech** (spaCy dependency parse):
  - Detects speech verbs (47 lemmas) with clausal complement (`ccomp`) children.
  - Captures the full subtree text of the complement clause.
  - Minimum 3-character threshold to skip trivially short spans.
- **Containment-aware overlap resolution**:
  - Sorted by start position, ties broken by span length (longest first).
  - Fully contained spans discarded; partial overlaps resolved by keeping the longer span.
- **Merge API**: `merge_dialogue()` combines direct + indirect turns with direct speech taking priority on overlapping spans.
- Returns `DialogueTurn` dataclasses with character offsets and `quote_style` (double, single, em_dash, indirect).

### 1.4 Speaker Attribution (`story_processing/nlp/speaker_resolver.py`)
- Dependency-parse based resolution using spaCy (`nsubj` / `nsubjpass` relations).
- 40+ speech verbs recognized (both lemma and inflected forms).
- Looks at current, previous, and next sentences for speech verb context.
- Walks relative/adverbial clause heads for nested verb structures.
- **Cross-sentence pronoun resolution**: builds a document-level mention chain of all PROPN tokens; backward scan from pronoun position (up to 3 sentences back) prefers PERSON-entity proper nouns, falls back to nearest PROPN.
- Incrementing `unknown_speaker_X` label for unresolved speakers.

### 1.5 Cross-Scene Speaker Reconciliation (`story_processing/context.py`)
- **Global named-speaker registry**: collects all non-unknown speaker names across all scenes.
- **Proximity-based re-attribution**: for each `unknown_speaker_X`, checks if a named speaker from the global registry appears in the same sentence or 1–2 prior sentences (whole-word match); replaces the unknown label if found.
- **Global renumbering**: remaining unknown speakers are renumbered with a single global counter for consistency across scenes.

### 1.6 Structure Metrics (`story_processing/signals/structure_metrics.py`)
- Sentence-level: count, word count, average length, length variance.
- Short-sentence streak detection (≤5 words, minimum streak of 3).
- Weighted punctuation scoring (`!` = 1.5, `?` = 1.2, `…` = 1.0, `—` = 0.8), normalized per sentence.
- **Action verb density**: ratio of high-energy action verbs (70+ lemmas: run, sprint, dash, hit, punch, explode, etc.) to total word count.
- Dialogue signals: ratio (dialogue words / total words), turn count, average dialogue length.

### 1.7 Semantic (Emotion) Metrics (`story_processing/signals/semantic_metrics.py`)
- **GoEmotions classifier** (`SamLowe/roberta-base-go_emotions`): multi-label text classification with 28 GoEmotions labels mapped to 12 target categories via weighted mapping.
- **12 emotion categories**: anxiety, joy, sadness, anger, calm, neutral, surprise, disgust, love, anticipation, nostalgia, confusion.
- **Weighted category mapping**: single-target labels map 1:1 (weight 1.0); multi-target labels split primary (0.7) and secondary (0.3) — e.g., "excitement" → joy (0.7) + anticipation (0.3).
- **Label integrity check**: validates on first load that the model's output labels are compatible with the weight mapping.
- **Sub-scene emotion arc**: chunks scene text (paragraph-split or sliding-window), runs batched inference, and produces per-chunk emotion scores.
- **Arc stabilization** with three mechanisms:
  - EMA smoothing (configurable alpha, default 0.3).
  - Peak detection threshold — new dominant emotion only assigned when top score exceeds runner-up by configurable gap (default 0.10).
  - Minimum segment duration — short emotion segments absorbed into longest neighbor.
- Sentence-transformer (`all-MiniLM-L6-v2`) retained for scene segmenter's semantic shift detection; LRU-cached encoding (256 entries, 512-token truncation).
- Singleton model loading (thread-safe) for both models.

### 1.8 AI Classification (`story_processing/ai/classifier.py`)
- LLM-powered scene classification producing: `primary_emotion`, `energy_level`, `emotion_intensity`, `scene_style`, `silence_intent`, `confidence_score`.
- **Context-aware prompts**: when `StoryContext` has history, the prompt includes a summary-level story context block (scene position, previous emotions, trend, pacing, known speakers) — Guardrail 4: summary-only, no raw score dumps.
- Two-attempt retry logic with descending confidence (0.85 → 0.70).
- Automatic fallback to heuristic rules on any LLM failure.
- Strict JSON-only output enforcement via prompt constraints.

### 1.9 Heuristic Fallback Classification (`story_processing/ai/fallback_rules.py`)
- Pure rule-based classification requiring no external services.
- **Configurable via `HeuristicConfig` dataclass**: all weights and thresholds are tunable without code changes.
- **Genre presets**: `DEFAULT_CONFIG`, `THRILLER_CONFIG` (higher arousal weight, lower action verb cap), `LITERARY_CONFIG` (lower punctuation weight, higher action threshold).
- **Multi-signal energy formula**: `w_punctuation * punct + w_variance * √variance + w_action_verbs * verb_density * 10 + w_arousal * arousal_boost + w_pacing * pacing + base`.
- **Weighted composite action score**: normalizes short-streak, punctuation, and action verb density to 0–1, applies configurable weights, compares against threshold — prevents single-signal spikes from overclassifying scenes as `action_heavy`.
- Scene style thresholds: `dialogue_driven` (>50% ratio), `narrative_heavy` (<10%), `action_heavy` (composite action score ≥ 0.45).
- Silence intent from short-sentence streaks and sentence density.
- **Continuous confidence scoring**: gap + absolute score formula with configurable min/max/scale, producing values in [0.20, 0.85].
- **Context-aware adjustments** (with guardrails):
  - Emotion momentum: boosts the previous dominant emotion when it has appeared in 2+ consecutive scenes and the gap between top emotions is tight or arousal is high (Guardrail 3); shift capped at ±0.15 (Guardrail 5).
  - Energy adjustment: +1.0 for escalating emotion trend in the back half of the story, +0.5 for accelerating pacing; total capped at ±1.5 (Guardrail 5).

### 1.10 Cross-Scene Context (`story_processing/context.py`)
- **`StoryContext` dataclass**: immutable per-scene snapshot with scene index, total scenes, position ratio, previous emotions (last 3), emotion/pacing trends, and known speakers.
- **`StoryContextBuilder`**: rolling-state builder (O(1) per scene) that tracks arousal history, dominant emotion history, word count history, and named speakers. Produces `StoryContext` for each scene.
- **Emotion trend**: computed from last 3 arousal values — escalating (monotonically increasing), de-escalating (monotonically decreasing), volatile (2+ label changes in 3 scenes), or stable.
- **Pacing trend**: computed from last 3 word counts — accelerating (decreasing word counts = shorter scenes), decelerating, or steady.

### 1.11 Audio Cue Extraction (`story_processing/nlp/audio_cue_extractor.py`)
- LLM-powered extraction of SFX events, ambience cues, and narration segment classification.
- Structured prompting: LLM acts as an audio sound designer.
- Extracts: `sfx_label`, `sfx_description`, `intensity`, `semantic_role`, `timing`, `order_hint`.
- Ambience cues: `primary_atmosphere`, `atmosphere_description`, `intensity`, `evolves`.
- Narration segments classified as: action, description, scene_setting, transition, inner_thought.
- Safe clamping of all enum values with graceful fallback on total failure.
- Retry logic (configurable `max_retries`, default 1).

### 1.12 Validation (`story_processing/validation/`)
- **Schema validation** — Pydantic v2 models enforce types, enums (12 emotions, 4 scene styles, 4 silence intents), numeric bounds, and required fields.
- **Logical consistency checks** — e.g., low dialogue ratio cannot be `dialogue_driven`, high energy + long sentences → cap energy.
- **Never-crash clamping** — invalid enums default to safe values, numeric fields clamped to valid ranges.
- Ultimate fallback returns safe neutral defaults if everything else fails.
- **Comprehensive schema models**: `NarrativePlan`, `Scene`, `SceneStructure`, `SceneSignals`, `SceneInterpretation`, `DialogueTurnSchema`, `SFXEventSchema`, `AmbienceCueSchema`, `NarrationSegmentSchema`, `EmotionArcEntry`.

### 1.13 DSL Compiler (`dsl/compiler.py` + `dsl/builders/`)
- Transforms Narrative Plan → Draft Timeline (multi-track audio project structure).
- **Track builder**: auto-creates narrator, per-character, music, ambience, and conditional SFX tracks with per-type EQ presets and gain defaults.
- **Voice clip builder**: interleaves narration and dialogue clips with scene-global ordering; separates speech attribution text from dialogue text; routes indirect speech to narrator track.
- **Music clip builder**: maps emotion → mood + energy → suffix (e.g., `tension_mid`, `uplifting_high`).
- **Ambience clip builder**: prefers LLM-extracted cues, falls back to emotion × style lookup table (24 exact mappings + emotion-only fallbacks).
- **SFX clip builder**: LLM-extracted events → clips with validated semantic roles; fallback: numeric thresholds for impact/texture SFX.
- **Settings builder**: global ducking (voice ducks background, with SFX-aware rules), dialogue compression, scene crossfade (duration from silence_intent), LUFS loudness normalization. Ducking amount adapts to average energy and dialogue-driven fraction.
- **Scene rules builder**: per-scene EQ tilt overrides (emotion-based: warm/neutral/bright) and ducking overrides (energy-based).

### 1.14 DSL Validation (`dsl/validator.py`)
- **Track purity checks**: one category per track, track existence verified against top-level definitions.
- **Voice clip guarantee**: warns if a scene has no voice clips.
- **Order continuity**: re-numbers voice clip `order` values to be sequential with no gaps.
- **Gain clamping**: track and clip gains clamped to [-30, +6] dB.
- **EQ preset validation**: unknown presets stripped, unknown tilts stripped.
- **Ducking validation**: per-scene duck_amount clamped to [-30, 0].
- **Final Pydantic validation** via `DraftTimeline` schema as safety net; returns best-effort on failure.

### 1.15 DSL Schema (`dsl/schema.py`)
- Full Pydantic v2 models for the Draft Timeline:
  - `DraftTimeline` (top-level), `DraftScene`, `DraftTrack`, `DraftClip`.
  - `ProjectConfig` (sample rate, bit depth — duration absent by design).
  - `DraftSettings`: `DuckingConfig` (with `DuckingRule`), `DialogueCompression`, `SceneCrossfade`, `LoudnessConfig`.
  - `SceneRules`: `SceneEQRules` (tilt, shelves), `SceneDuckingOverride`.
  - Typed enums: `TrackType`, `TrackRole`, `SFXSemanticRole`, `EQPreset`, `EQTilt`, `DuckingMode`.
- `DraftClip` supports multiple descriptor modes: voice (tts_text + order), music (mood + energy_hint + loop), ambience (atmosphere + loop), SFX (sfx_hint + semantic_role), plus common fields (eq_preset, loop, gain, fade_in, fade_out).

### 1.16 DSL Constants (`dsl/constants.py`)
- Deterministic mapping tables for the compiler: `EMOTION_TO_MOOD` (6 mappings), `ENERGY_SUFFIX_THRESHOLDS`, `EMOTION_TO_TILT`, atmosphere lookup (24 exact + 6 fallback + default), EQ preset defaults per track type, gain defaults (narrator/character/SFX at 0 dB, music base -9 dB, ambience base -15 dB with energy scaling), music volume scaling, silence-to-crossfade mapping, SFX trigger thresholds, ducking defaults.

### 1.17 Multi-LLM Support (`story_processing/ai/llm_client.py`)
- Abstract `LLMClient` interface with three implementations:
  - **LocalLLMClient** — Ollama-compatible (Qwen3 support with `<think>` tag stripping, `/no_think` prefix).
  - **OpenAIClient** — OpenAI-compatible API (supports vLLM, LM Studio, etc.) with JSON response format.
  - **GeminiClient** — Google Gemini via `google-genai` SDK with `response_mime_type="application/json"`.
- All enforce `temperature=0`, `top_p=1` for deterministic outputs.

### 1.18 Pipeline Orchestration (`story_processing/pipeline.py`)
- Full end-to-end pipeline: detect format → preprocess → spaCy NLP → extract dialogue (direct + indirect + merge) → segment scenes → parallel per-scene extraction → reconcile speakers → sequential classification with cross-scene context → audio cue extraction → validate → assemble.
- **Format detection on raw input** (before normalization strips indentation cues).
- **Parallel per-scene processing** via `ThreadPoolExecutor` for structure/signal extraction.
- **Cross-scene context builder** integrated: `StoryContextBuilder` produces per-scene context; classification receives `StoryContext`.
- **Global speaker reconciliation** after parallel extraction, before classification.
- **Deterministic scene IDs**: content-based SHA-256 hash for reproducibility.
- Sequential AI classification + audio cue extraction to respect LLM throughput limits.
- JSON serialization via `orjson` for high performance.

### 1.19 CLI (`cli.py`)
- Full `argparse`-based CLI registered as `audstories` console script.
- **`audstories process`**: single file processing with `--input`, `--output`, `--model`, `--no-llm` options.
- **`audstories batch`**: directory batch processing — processes all `.txt` files, each into a sub-directory, with success/failure summary.
- **Model auto-detection**: `gpt-*`/`o1*`/`o3*`/`o4*` → OpenAI, `gemini*` → Gemini, anything else → local Ollama.
- Default model: `gemini-2.0-flash`.
- Outputs both `narrative_plan.json` and `draft_timeline.json`.
- `.env` file loading via `python-dotenv`.

### 1.20 Test Suite (`tests/`)
- **18 test files** covering all major modules:
  - `test_normalizer.py` — text preprocessing.
  - `test_scene_segmenter.py` — scene segmentation.
  - `test_dialogue_extractor.py` — dialogue extraction.
  - `test_speaker_resolver.py` — speaker attribution.
  - `test_structure_metrics.py` — structure signals.
  - `test_classifier.py` — AI classification.
  - `test_fallback_rules.py` — heuristic fallback.
  - `test_context.py` — cross-scene context.
  - `test_narrative_plan.py` — narrative plan assembly.
  - `test_story_validation.py` — validation layer.
  - `test_compiler.py` — DSL compiler.
  - `test_dsl_builders.py` — DSL builders (tracks, clips, settings, scene rules).
  - `test_dsl_constants.py` — DSL constants and mapping tables.
  - `test_dsl_validator.py` — Draft Timeline validation.
  - `test_pipeline_contract.py` — cross-layer pipeline contracts.
  - `test_cli_smoke.py` — CLI smoke tests.
  - `test_determinism.py` — determinism / reproducibility tests.
- Session-scoped spaCy fixture (`en_core_web_sm`) for fast test execution.
- `MockLLMClient` for unit tests that need LLM interaction without real API calls.
- Pytest markers: `slow`, `spacy`, `contract`.

### 1.21 Packaging (`pyproject.toml`)
- `setuptools` build backend.
- Package name: `audstories`, version `1.0.0`.
- Python ≥ 3.10 required.
- Dependencies: spacy, sentence-transformers, transformers, pydantic, numpy, orjson, httpx, google-genai, python-dotenv.
- Test optional dependencies: pytest, pytest-xdist, en-core-web-sm.
- Console script entry point: `audstories = cli:main`.

---

## 2. Current Drawbacks

### 2.1 Speaker Attribution Limitations
- **Limited coreference resolution**: Pronouns are resolved via a backward mention-chain scan (up to 3 sentences back), preferring PERSON-entity proper nouns. However, there is no full coreference resolution model (e.g., `neuralcoref`, `coreferee`, or transformer-based coref) — the chain is purely PROPN-based with no semantic matching.
- **Screenplay-format blindness**: The engine doesn't parse standard screenplay formats (e.g., `AYAAN:` or `AYAAN (murmuring)` on their own line) — it only finds quoted and indirect dialogue.
- **Unknown speaker proliferation**: Despite global renumbering and proximity-based re-attribution, scenes without nearby named speakers will still generate `unknown_speaker_X` labels. The reconciliation relies on exact name match in nearby sentences, which misses cases where the speaker is referenced by title, nickname, or description.

### 2.2 Scene Segmentation Gaps
- **Semantic shift sensitivity**: The paragraph-embedding threshold (default 0.35 distance) can be either too sensitive (fragmenting scenes mid-paragraph) or too conservative (missing subtle shifts) depending on the writing style. No automatic threshold tuning.
- **Format detection heuristics**: The indent/block/unknown detection uses simple ratio heuristics (indent ratio ≥ 0.35, blank ratio ≥ 0.20) which may misclassify mixed-format documents or texts with inconsistent formatting.
- **Single-language support**: All regex patterns and NER are English-only.
- **No score transparency**: Break candidates are scored internally but the final output doesn't expose which signals fired or their scores — makes debugging difficult.

### 2.3 Dialogue Extraction Fragility
- **Nested quotes**: `"He said 'hello'"` may produce unexpected results from the overlap resolver depending on span lengths.
- **Indirect speech over-extraction**: The `ccomp` dependency pattern can match non-speech constructions (e.g., "She knew that the answer was wrong") — the verb lemma filter helps but isn't perfect.
- **No screenplay/script format support**: Does not detect character-name header lines followed by dialogue text.
- **Apostrophe edge cases**: Single-quote pattern (minimum 2 chars, whitespace boundaries) is a heuristic that can still match possessives in edge cases.

### 2.4 Emotion Analysis Weaknesses
- **GoEmotions model limitations**: While a significant upgrade from cosine-similarity anchors, the model was trained on Reddit comments (GoEmotions dataset), not literary text. Performance on nuanced narrative prose may differ from the training distribution.
- **128-token truncation**: The emotion classifier truncates at 128 tokens (`_EMOTION_MAX_LENGTH`), which may lose important context in long paragraphs.
- **Arc stabilization can over-smooth**: EMA smoothing with alpha=0.3 means each chunk carries 70% of the previous chunk's influence, which can mask genuine rapid emotional shifts (e.g., surprise twists).
- **Scene-level aggregation by mean**: The final scene-level emotion scores are a mean of the stabilized arc chunks. This loses the shape of the arc — a scene that starts sad and ends joyful gets "moderate sadness + moderate joy" rather than capturing the transition.

### 2.5 Heuristic Fallback Assumptions
- **Energy formula weights are defaults**: While configurable via `HeuristicConfig`, the default weights (`w_punctuation=2.0`, `w_action_verbs=2.5`, etc.) were not empirically tuned against labeled data.
- **Genre presets are limited**: Only 3 presets (default, thriller, literary); no mechanism to auto-detect genre or allow user-specified config files for custom tuning.
- **Context guardrails may be too conservative**: The momentum activation requires 2 consecutive scenes with the same emotion before boosting, which means it never activates for stories with varied scene emotions (which is most stories).

### 2.6 DSL Compiler Limitations
- **No timing information**: Draft Timeline has no `start`, `duration`, or `offset` — entirely dependent on a downstream Asset Resolver.
- **Single music clip per scene**: Cannot express music transitions, layering, or dynamic changes within a scene.
- **No pause/silence clips**: The `silence_intent` signal is computed but only used for scene crossfade duration — no explicit silence clips are generated between dialogue turns.
- **No volume automation**: Music and ambience gains are static per-scene; no fade-in/out within scenes except global crossfade.
- **Atmosphere mapping gaps**: Only 6 emotions have atmosphere mappings in the lookup table. The 6 new emotions (surprise, disgust, love, anticipation, nostalgia, confusion) fall through to `neutral_room` default.
- **Music mood mapping gaps**: Only 6 emotions have mood mappings. The 6 new emotions also fall through to `neutral`.

### 2.7 Performance Concerns
- **Two heavyweight models**: `en_core_web_lg` (~560 MB) + GoEmotions classifier (~500 MB) + `all-MiniLM-L6-v2` (~80 MB). First run is slow; total memory footprint is significant.
- **Sequential LLM calls**: Classification + audio cue extraction run sequentially per scene. For stories with many scenes, this becomes a bottleneck.
- **No model selection via config**: spaCy model is hardcoded to `en_core_web_lg` in the pipeline (though parameterized); GoEmotions model name is a module-level constant.

### 2.8 Validation Gaps
- **No end-to-end validation**: The pipeline validates interpretation and Draft Timeline separately, but doesn't validate that the Narrative Plan → Draft Timeline transformation preserved semantic correctness (e.g., every speaker in the plan has a track in the timeline).
- **Silent clamping**: Most validation errors are silently clamped with a log warning rather than reported to the user — a scene classified as `"romantic"` (invalid) silently becomes `"neutral"`.

### 2.9 Missing Features
- **No character voice profiles**: No mechanism to assign voice attributes (pitch, speed, tone, accent) per character.
- **No narrative arc tracking**: While per-scene emotion arcs exist, there's no story-wide tension curve or narrative structure detection.
- **No multi-language support**: All NLP is English-only.
- **No streaming/incremental processing**: The entire story must be provided upfront.
- **No export formats beyond JSON**: No YAML, XML/EDL (for DAW import), or visual timeline preview.

---

## 3. How to Handle These Drawbacks

### 3.1 Speaker Attribution → Full Coreference
- **Short-term**: Integrate a dedicated coreference resolution model (e.g., `fastcoref`, `maverick-coref`) as an optional pipeline step in `speaker_resolver.py`. This would handle "he", "she", "they" resolution across sentences with semantic understanding.
- **Medium-term**: Use the LLM to resolve ambiguous speakers in a second pass — send the scene text + extracted dialogue turns and ask "who is speaking each line?". The `StoryContext.known_speakers` already provides the character list needed.

### 3.2 Scene Segmentation → Configurable + Diagnostic
- **Short-term**: Expose break candidate scores in the output (add a `segmentation_diagnostics` field) so users can see why scenes were split and tune thresholds.
- **Medium-term**: Add automatic threshold calibration based on text length and density — shorter texts need lower thresholds, longer texts can use higher ones.
- **Long-term**: Train a lightweight binary classifier on paragraph boundaries using labeled data to replace/supplement the rule-based scoring.

### 3.3 Dialogue Extraction → Multi-Format Support
- **Short-term**: Add a screenplay/script parser mode that detects `CHARACTER_NAME` header lines followed by dialogue text. This would handle `story/scene1.txt`'s format.
- **Medium-term**: Build a hybrid extractor that tries screenplay format first, then falls back to quote-based + indirect extraction.

### 3.4 Emotion Analysis → Better Model + Longer Context
- **Short-term**: Increase `_EMOTION_MAX_LENGTH` from 128 to 256 or 512 tokens for better context capture. Add a scene-level "emotion trajectory" summary (e.g., "transitions from sadness to joy") alongside the mean scores.
- **Medium-term**: Fine-tune the GoEmotions model on a literary/narrative dataset, or swap to a model trained on longer-form text.
- **Long-term**: Per-sentence emotion tracking with a rolling window that feeds into a scene-level emotion trajectory descriptor.

### 3.5 Heuristic Fallback → Configurable + Data-Driven
- **Short-term**: Expose `HeuristicConfig` as a YAML/JSON config file loadable from the CLI. Add genre auto-detection (e.g., from dialogue ratio, action verb density, average sentence length) to select the appropriate preset.
- **Medium-term**: Use a lightweight decision-tree or gradient-boosted classifier trained on labeled examples to replace the rule-based fallback.

### 3.6 DSL Compiler → Richer Mappings + Timeline Features
- **Short-term**: Extend `EMOTION_TO_MOOD` and `_ATMOSPHERE_EXACT` to cover all 12 emotions. Generate explicit silence/pause clips between dialogue turns based on `silence_intent`.
- **Medium-term**: Support multiple music clips per scene (intro, body, outro) with crossfade transitions. Add volume automation envelopes.

### 3.7 Performance → Lazy Loading + Batching + Async
- **Short-term**: Allow GoEmotions model name and spaCy model name selection via CLI/env vars. Support `en_core_web_sm` for faster processing when accuracy isn't critical.
- **Medium-term**: Batch LLM calls — send multiple scenes in a single prompt (where context window allows) to reduce round trips.
- **Long-term**: Async pipeline with `asyncio` + `httpx.AsyncClient` for concurrent LLM calls.

### 3.8 Validation → Transparent + Cross-Layer
- **Short-term**: Add a "validation report" to the output that lists all clamped values, warnings, and fallbacks applied — make silent clamping visible.
- **Medium-term**: Add cross-layer validation between Narrative Plan and Draft Timeline (e.g., every speaker has a track, every scene has clips).

---

## 4. What We Can Add to Make It Better

### 4.1 Screenplay / Script Format Parser
The `story/scene1.txt` file demonstrates a screenplay format that the current engine cannot parse. Adding a dedicated screenplay parser would:
- Detect `CHARACTER_NAME` header lines and associate them with the following dialogue.
- Parse parenthetical stage directions `(murmuring, almost to himself)` as acting cues.
- Extract `(O.S.)`, `(V.O.)` markers for off-screen/voice-over annotations.
- Handle `FADE OUT`, `CUT TO`, `INT.`/`EXT.` scene headers.

### 4.2 Character Voice Profile System
- Create a character registry that persists across scenes.
- Assign voice attributes (pitch, speed, tone, accent, gender) per character.
- Include these profiles in the Draft Timeline so the TTS/Asset Resolver can assign distinct voices.
- Support a `voices.json` config file for user-defined voice mappings.

### 4.3 Emotional Arc / Tension Curve
- Compute a story-wide tension curve from per-scene energy + emotion data.
- Apply narrative structure models (three-act structure, hero's journey) to detect climax, resolution, etc.
- Use the arc to auto-adjust music intensity, ambience evolution, and pacing.
- Include the arc as a top-level field in the Narrative Plan (`"arc": {"tension_curve": [0.3, 0.5, 0.8, 0.4]}`).

### 4.4 Sound Design Intelligence
- **Foley extraction**: Detect verbs that imply sounds ("footsteps slow", "bench creaks", "wind moves") using verb-object dependency patterns, not just LLM.
- **Sound layering rules**: Multiple ambience layers (e.g., distant traffic + crickets + wind) instead of a single atmosphere tag.
- **Dynamic SFX timing**: Link SFX events to specific words/clauses in the narration timeline for precise placement.

### 4.5 Multi-Language Support
- Abstract all regex patterns behind a language adapter interface.
- Add language detection (using `langdetect` or spaCy's language models).
- Support at least: English, Hindi, Spanish for the PCDDJ Engine's target audience.

### 4.6 Streaming / Incremental Processing
- Process the story in chunks as it's being written/received.
- Emit partial Narrative Plan updates as scenes are completed.
- Useful for real-time collaboration or long-form content.

### 4.7 Configuration System
- Replace remaining hardcoded constants with a layered config system (defaults → project config → CLI overrides).
- Configurable: GoEmotions model name, emotion category weights, dialogue ratio thresholds, energy formula weights, EQ presets, ducking defaults, atmosphere mappings, silence-to-crossfade mappings, semantic shift threshold, break score threshold.
- Support YAML or TOML config files.

### 4.8 Quality Scoring & Diagnostics
- Generate a per-scene quality report: how confident is the engine in its classification? Where did it fall back to heuristics? Which speakers were unresolved? What segmentation signals fired?
- Include a `diagnostics` section in the Narrative Plan output.
- Flag scenes that might need human review (e.g., low confidence + many unknown speakers).

### 4.9 Asset Resolver Integration Points
- Define a clear interface/contract for the downstream Asset Resolver.
- Add `tts_voice_id` hints in voice clips (from the character profile system).
- Add `music_search_tags` alongside the mood string for more flexible asset matching.
- Add `sfx_search_tags` alongside the hint label for sound library queries.

### 4.10 Batch / Multi-Story Processing
- ✅ Basic batch processing implemented (`audstories batch`).
- **Next**: Generate a unified project with multiple episodes/chapters sharing the same character registry and voice profiles.
- Produce a manifest file listing all generated timelines.

### 4.11 Observability & Logging
- Structured logging (JSON format) with scene IDs for easy filtering.
- Timing metrics per pipeline stage (preprocessing: Xms, NLP: Xms, classification: Xms, etc.).
- LLM token usage tracking for cost estimation.

### 4.12 Export Formats
- Support alternative output formats beyond JSON: YAML, XML (for DAW import), EDL (Edit Decision List).
- Generate a human-readable script/screenplay from the Narrative Plan (reverse transformation for review).
- Export a visual timeline preview (HTML/SVG) showing tracks, clips, and scenes.

---

## 5. Priority Recommendations

| Priority | Improvement | Impact | Effort | Status |
|----------|-------------|--------|--------|--------|
| ✅ Done | CLI with file input | Basic usability | Low | Implemented |
| ✅ Done | Unit test suite | Reliability & refactoring safety | Medium | 18 test files |
| ✅ Done | Expanded emotion categories (6 → 12) | Richer emotion detection | Low | Implemented |
| ✅ Done | Cross-scene context system | Story-aware classification | Medium | Implemented |
| ✅ Done | Speaker reconciliation | Character continuity | Medium | Implemented |
| ✅ Done | Deterministic scene IDs | Reproducibility | Low | Implemented |
| ✅ Done | Heuristic config + genre presets | Flexibility & tuning | Medium | Implemented |
| ✅ Done | Indirect speech extraction | Better dialogue coverage | Medium | Implemented |
| ✅ Done | Semantic scene segmentation | Smarter scene splits | Medium | Implemented |
| ✅ Done | Action verb density | Better energy/action detection | Low | Implemented |
| ✅ Done | Emotion arc with stabilization | Sub-scene granularity | Medium | Implemented |
| ✅ Done | DSL validation | Compiler safety | Medium | Implemented |
| ✅ Done | Batch processing | Multi-file support | Low | Implemented |
| 🔴 High | Screenplay format parser | Unlocks `scene1.txt`-style input | Medium | Not started |
| 🔴 High | DSL mood/atmosphere for all 12 emotions | Complete audio coverage | Low | Not started |
| 🟠 Medium | Full coreference resolution | Better speaker attribution | Medium | Not started |
| 🟠 Medium | Configuration file system (YAML/TOML) | User-level flexibility | Medium | Not started |
| 🟠 Medium | Character voice profiles | Production-ready output | Medium | Not started |
| 🟠 Medium | Narrative arc tracking | Story-aware output | Medium | Not started |
| 🟠 Medium | Validation diagnostics/report | Transparency | Low | Not started |
| 🟡 Low | Multi-language support | Broader audience | High | Not started |
| 🟡 Low | Streaming processing | Real-time use cases | High | Not started |
| 🟡 Low | Export formats (YAML, EDL, HTML) | Interoperability | Medium | Not started |
| 🟡 Low | Async LLM pipeline | Performance at scale | Medium | Not started |
