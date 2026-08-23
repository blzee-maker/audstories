# Story-to-Script Engine — Detailed Drawbacks

A thorough breakdown of every known limitation in the current codebase, why it matters, and what goes wrong because of it.

---

## 1. Speaker Attribution Limitations

**Affected file**: `story_processing/nlp/speaker_resolver.py`

### 1.1 ~~No~~ Cross-Sentence Coreference Resolution — **Fixed**

> **Status**: Resolved. `_find_proper_noun_near()` now performs a backward
> mention-chain scan across previous sentences when no PROPN is found in the
> pronoun's own sentence.

The resolver previously only looked for proper nouns within the **same sentence** as a pronoun. If the speaker was established in one sentence and referred to by pronoun in the next, the resolver failed.

**What changed**: A document-level mention chain (`_build_mention_chain`) is built once per `resolve_speakers()` call, indexing every PROPN token with its position and whether spaCy's NER labels it as a PERSON entity. `_find_proper_noun_near()` now:

1. Tries the **same-sentence scan** first (fast path, preserving original behaviour).
2. Falls back to a **backward mention-chain scan** — walking the chain in reverse from the pronoun's token index, within a configurable lookback window (default: 3 sentences). PERSON-entity PROPNs are preferred over bare PROPNs.

**Example that now works**:

```
Ayaan looked at the bench.
"I should sit down," he said.
```

The mention chain contains `Ayaan` (PERSON entity, sentence 0). When `"he"` is encountered in sentence 1, the backward scan finds `Ayaan` within the 1-sentence lookback and returns it instead of the raw pronoun.

**Remaining limitation**: This is still a heuristic, not true coreference resolution. It picks the nearest PERSON PROPN in previous sentences, which can be wrong in multi-character scenes where several characters are mentioned close together. A full neural coreference model (e.g. `coreferee` or `neuralcoref`) would be more accurate but adds a dependency and latency.

### 1.2 Screenplay / Script Format Blindness

The dialogue extractor (which feeds the speaker resolver) only looks for quoted text: `"…"`, `'…'`, or `— …`. Standard screenplay format, which the project's own `story/scene1.txt` uses, is completely ignored.

**Example from `story/scene1.txt`**:

```
AYAAN
(murmuring, almost to himself)
Still my favorite place to disappear.
```

This is **never** extracted as dialogue. The engine sees `"Still my favorite place to disappear."` as a plain narration sentence. Every line of dialogue in this 154-line story file is invisible to the pipeline.

**Impact**: The Narrative Plan for `scene1.txt` would report zero dialogue turns, 0% dialogue ratio, and zero speakers — producing a completely wrong scene classification and a draft timeline with only a narrator track.

### 1.3 Unknown Speaker Proliferation

Every unresolved dialogue turn gets a monotonically incrementing label: `unknown_speaker_1`, `unknown_speaker_2`, etc. There is no attempt to cluster unknown speakers or infer that two unknown turns might be from the same person.

**Example**:

```
"Watch out!" someone yelled.
"I see it," came the reply.
"Run!" the voice shouted again.
```

If no speech verb + `nsubj` is found for any of these, they become `unknown_speaker_1`, `unknown_speaker_2`, `unknown_speaker_3` — generating three separate voice tracks in the Draft Timeline for what is likely two characters (or even one).

**Impact**: The compiled timeline ends up with unnecessary tracks. Each gets its own TTS voice, creating a cacophony of distinct voices for what should be one or two characters.

---

## 2. Scene Segmentation Gaps

**Affected file**: `story_processing/nlp/scene_segmenter.py`

### 2.1 ~~Fixed and Limited Temporal Markers~~ — **Fixed**

> **Status**: Resolved. The segmenter now uses a multi-signal, confidence-scored
> architecture with greatly expanded temporal detection.

The temporal gap regex previously covered only a narrow list of phrases (`the next morning`, `hours later`, `meanwhile`, etc.) and missed numeric time skips, sleep/waking transitions, event-based transitions, seasonal shifts, and generic time-skip openers.

**What changed**: `_TEMPORAL_RE` was expanded from ~10 patterns to 50+ patterns across six categories:

| Category | Example Patterns Now Matched |
|---|---|
| Numeric time skips | `"Three years passed"`, `"10 minutes later"`, `"several decades went by"` |
| Sleep / waking | `"When she woke up"`, `"He fell asleep"`, `"opened her eyes"` |
| Event-based | `"After the funeral"`, `"Once the trial ended"`, `"By the time he returned"` |
| Seasonal / temporal | `"It was winter now"`, `"Spring had come"`, `"That summer"` |
| Generic time-skip | `"Time passed"`, `"Much later"`, `"In the days that followed"` |
| NER-assisted (new) | spaCy DATE/TIME entities at sentence starts (e.g. `"In 1987"`, `"On Tuesday"`) |

Additionally, temporal phrases now feed into a **confidence scoring system** (score: 0.65) that stacks with other signals, rather than being a standalone binary break trigger. A spaCy DATE/TIME NER layer (score: 0.40) acts as a supplementary signal for patterns regex can never cover.

**Remaining limitation**: Metaphorical transitions like `"The next chapter of her life"` are still not detected — these require deeper semantic understanding and would produce false positives if matched by regex (e.g., a book literally about chapters).

### 2.2 ~~No Semantic Scene Detection~~ — **Fixed**

> **Status**: Resolved. The segmenter now includes paragraph-level embedding
> similarity detection and Normal Indent format awareness.

The segmenter previously used only surface-level patterns (regex on markers, triple-newlines, temporal phrases) with no understanding of what is happening in the story.

**What changed — two new detection layers**:

**A. Normal Indent Format Detection** (`detect_format()`):

The segmenter now recognises the **Normal Indent** novel formatting convention where paragraphs start with indentation (tab or spaces) and blank lines signal scene breaks — as opposed to Block format where blank lines are just paragraph separators. A `detect_format()` function analyses line-start indentation patterns on the raw text (before normalisation strips whitespace cues):

- **Indent format detected** → every blank line (`\n\n`) becomes a high-confidence scene break candidate (score: 0.85).
- **Block format detected** → blank lines are ignored; only explicit markers, temporal phrases, and semantic shifts trigger breaks.
- **Unknown** → falls back to auto-detection within the segmenter.

Format detection runs in `pipeline.py` on the raw input text, then passes the result as `format_hint` to `segment_scenes()`.

**B. Semantic Shift Detection** (`_detect_semantic_breaks()`):

Consecutive paragraphs are encoded using the sentence-transformer model already loaded by `semantic_metrics.py` (no new model, no new dependency). When the cosine distance between adjacent paragraph embeddings exceeds a threshold (default: 0.35), a scene break candidate is registered (score: 0.55).

**Example that now works**:

```
They laughed together at the café, the afternoon sun warm on their faces.

The detective slammed the folder on the table. "We know you were there."
```

The café paragraph embedding ≈ joy/warmth; the interrogation paragraph embedding ≈ anger/tension. The cosine distance is well above 0.35, producing a semantic shift break. Combined with any other signal (temporal phrase, blank line in indent format), the cumulative score easily exceeds the break threshold.

**C. Multi-Signal Confidence Scoring**:

The entire segmenter was rewritten around a scoring system. Each candidate boundary accumulates a confidence score from every layer that fires at that offset:

| Signal | Score | Notes |
|---|---|---|
| Explicit marker (`Chapter`, `---`, `***`) | 1.0 | Always fires |
| Blank line in Normal Indent format | 0.85 | Format-dependent |
| Triple-newline structural break | 0.75 | Always a strong signal |
| Expanded temporal phrase match | 0.65 | Regex Layer 3a |
| Semantic embedding shift | 0.55 | Content-based Layer 4 |
| spaCy DATE/TIME entity at sentence start | 0.40 | NER-assisted Layer 3b |

Scores stack additively (capped at 1.0). A break fires when cumulative score ≥ `break_threshold` (default: 0.55, configurable). This replaces the old binary break/no-break system.

**D. Normaliser fix**: `normalizer.py` previously collapsed `\n{3,}` → `\n\n`, destroying triple-newline signals before the segmenter could see them. Now collapses `\n{4,}` → `\n\n\n`, preserving the distinction between paragraph breaks and major structural breaks.

**Remaining limitations**:
- Semantic shift detection adds latency proportional to paragraph count (one embedding per paragraph). Can be disabled via `semantic=False` on `segment_scenes()`.
- Format detection is heuristic — text that mixes indent and block styles within the same document may be misclassified.
- The scoring weights are hand-tuned; optimal values may vary by genre.

### 2.3 English-Only Patterns

Every regex — markers, temporal phrases, structural breaks — is written exclusively for English. There is no language detection, no pattern abstraction, and no way to plug in alternative pattern sets.

**Impact**: The engine silently produces bad results on non-English text. It won't crash, but it will treat the entire text as a single scene with zero detected dialogue, because none of the quote patterns or scene markers will fire.

---

## 3. Dialogue Extraction Fragility

**Affected file**: `story_processing/nlp/dialogue_extractor.py`

### 3.1 No Screenplay / Script Format Support

The extractor has exactly three regex patterns:

```python
_DOUBLE_QUOTE_RE = re.compile(r'"([^"]+)"')           # "…"
_SINGLE_QUOTE_RE = re.compile(r"'([^']{2,})'")        # '…'
_EM_DASH_RE = re.compile(r"(?:^|\n)\s*[—–]\s*(.+?)(?=\n|$)")  # — …
```

None of these match screenplay-format dialogue where a character name appears on its own line followed by their speech on the next line(s). This is the format used in the project's own `story/scene1.txt`:

```
SAANVI
(smiling, but distant)
Every day.
Just... not always like this.
```

The extractor sees none of this as dialogue.

### 3.2 ~~Nested Quote Extraction Errors~~ — **Fixed**

> **Status**: Resolved. The overlap resolver was replaced with a
> containment-aware algorithm.

Previously the overlap resolver was a simple linear sweep that kept the earliest match. Partial overlaps where neither span contained the other were handled incorrectly.

**What changed**: `_resolve_overlaps()` now sorts matches by `start_char` (breaking ties by span length, longest first) and handles three cases explicitly:

1. **Full containment** (match B is inside match A) → discard B unconditionally.
2. **Partial overlap** (neither contains the other) → keep the longer span (more likely to be real dialogue).
3. **No overlap** → keep both.

The function signature and return type are unchanged — this is a drop-in replacement within `dialogue_extractor.py`.

### 3.3 ~~Apostrophe / Contraction Collisions~~ — **Fixed**

> **Status**: Resolved. The single-quote regex was replaced with a
> boundary-constrained pattern.

The old regex `'([^']{2,})'` matched across archaic contractions (`'Twas...'tis`) and had no boundary constraints.

**What changed**: The new `_SINGLE_QUOTE_RE` pattern:

```python
_SINGLE_QUOTE_RE = re.compile(
    r"(?:(?<=\s)|(?<=^))"        # opening ' must follow whitespace or start-of-string
    r"'([^'\n]{2,})'"             # content: 2+ non-quote, non-newline chars
    r'(?=[\s.,!?;:\-)}\]—–"]|$)', # closing ' must precede punctuation/whitespace/end
    re.MULTILINE,
)
```

Key improvements:

- **Lookbehind on opening quote**: prevents matching mid-word contractions.
- **No cross-line matching**: `[^'\n]` prevents spans from crossing line boundaries.
- **Lookahead on closing quote**: requires whitespace or punctuation after the closing `'`.

The `'Twas the night before — 'tis` example no longer false-matches because `'Twas` is not preceded by whitespace (or start-of-string in context where it follows another `'`).

### 3.4 ~~No Indirect Speech Detection~~ — **Fixed**

> **Status**: Resolved. A new `extract_indirect_speech()` function uses
> spaCy dependency parsing to detect reported speech.

The extractor previously ignored indirect/reported speech entirely.

**What changed**: A new function `extract_indirect_speech(doc: Doc)` walks the spaCy dependency tree looking for speech/communication verbs (`say`, `tell`, `explain`, `admit`, `claim`, etc. — 40+ lemmas) with a `ccomp` (clausal complement) child. The complement subtree's text is captured as a `DialogueTurn` with `quote_style="indirect"`.

**Data type updates**:

- `DialogueTurn.quote_style` now includes `"indirect"` as a literal value.
- `AttributedTurn` in `speaker_resolver.py` gained a `quote_style: str = "double"` field, passed through from the `DialogueTurn`.
- `DialogueTurnSchema` in `schema.py` gained a `quote_style` field with allowed values `"double"`, `"single"`, `"em_dash"`, `"indirect"`.

**Pipeline integration**: `pipeline.py` calls `extract_indirect_speech(doc)` after the regex extraction, then merges results via `merge_dialogue()` — the same containment-aware overlap resolver from the 3.2 fix. Direct-quote matches take priority over indirect at the same span.

**DSL compiler handling**: In `build_voice_clips()`, turns with `quote_style="indirect"` are routed to the **narrator track** (indirect speech is narrated, not voiced as a character). The full sentence is emitted as a single narration clip. This keeps indirect speech counted in dialogue metrics while producing the correct audio routing.

**Example that now works**:

```
She told him that the meeting was cancelled.
He explained how the system worked.
```

Both sentences are now captured as indirect `DialogueTurn` instances, contributing to `dialogue_ratio` and `dialogue_turn_count` for the scene.

**Remaining limitation**: The `ccomp` heuristic may miss complex sentence structures where the clausal complement is deeply nested or rephrased (e.g., `"According to sources, the deal fell through"` — no speech verb governs a `ccomp` here). A more sophisticated approach would require semantic role labelling.

---

## 4. Emotion Analysis Weaknesses

**Affected file**: `story_processing/signals/semantic_metrics.py`

### 4.1 ~~Only Six Emotion Categories~~ — **Fixed**

> **Status**: Resolved. The emotion model now uses 12 categories powered by
> a dedicated GoEmotions classifier with weighted category mapping.

The emotion model was previously defined by six static anchor phrases (`anxiety`, `joy`, `sadness`, `anger`, `calm`, `neutral`). A horror scene got bucketed into `anxiety`; a romantic first-kiss scene got `joy` — the closest available categories but not the right ones for music mood or ambience selection.

**What changed — 12 emotion categories via GoEmotions**:

The `EMOTION_ANCHORS` dict and the cosine-similarity-to-anchor approach were removed entirely. In their place, a dedicated multi-label emotion classifier (`SamLowe/roberta-base-go_emotions`) outputs proper sigmoid probabilities across 28 GoEmotions labels. These are aggregated into 12 target categories via a `GOEMOTION_WEIGHTS` weighted mapping:

| Category | GoEmotions Sources |
|---|---|
| anxiety | fear, nervousness |
| joy | joy, amusement, excitement, optimism, pride, relief |
| sadness | sadness, grief, disappointment, remorse |
| anger | anger, annoyance, disapproval |
| calm | approval, gratitude, caring |
| neutral | neutral, realization |
| surprise | surprise, curiosity |
| disgust | disgust, embarrassment |
| love | love, admiration, desire |
| anticipation | curiosity, excitement, desire, optimism |
| nostalgia | grief, remorse, caring |
| confusion | confusion |

Where a GoEmotions label maps to multiple target categories (e.g. `excitement` → `joy` + `anticipation`), a **weighted split** preserves peaks: the primary target gets 0.7 of the probability, the secondary gets 0.3. This avoids the dilution that equal splitting would cause.

**Downstream updates**: The `EmotionType` literal in `schema.py`, the `_EMOTIONS` tuples in `fallback_rules.py` and `validator.py`, and the classification prompt in `prompt_templates.py` were all expanded to include the six new categories.

**Label integrity safety net**: The classifier singleton performs a label compatibility check on first load — if someone swaps `_EMOTION_MODEL_NAME` to a model that doesn't output the expected 28 GoEmotions labels, a `RuntimeError` fires immediately with the exact missing labels listed, rather than silently zeroing out unmapped categories.

**Remaining limitation**: The weighted mapping is hand-tuned. Some GoEmotions labels (e.g. `excitement`) are genuinely ambiguous — a "first kiss" excitement is narratively different from a "battle preparation" excitement, but the weights are static. A future improvement would be context-aware aggregation where co-occurring labels influence the primary/secondary split.

### 4.2 ~~Scene-Level Granularity Only~~ — **Fixed**

> **Status**: Resolved. A new `compute_emotion_arc()` function provides
> per-chunk emotion scoring with configurable chunking strategies and
> a mandatory stabilization layer.

Emotion scores were previously computed by encoding the **entire scene text** as a single vector. A scene that started with joy and ended with grief resolved to `neutral` — the least useful classification for audio production.

**What changed — sub-scene emotion arcs**:

A new `compute_emotion_arc()` function in `semantic_metrics.py` chunks the scene text, classifies each chunk via batched inference, and produces a per-chunk emotion arc alongside the scene-level aggregate.

Two configurable chunking strategies are supported:

- **paragraph** (default): Splits on blank lines. Good for scenes with clear paragraph structure.
- **sliding_window**: Overlapping windows of N sentences (default 3) with stride 1. Finer granularity for continuous prose.

**Example that now works**:

```
She laughed as they danced under the fairy lights.
Then the phone rang.
"It's the hospital," he said. "Your mother didn't make it."
```

With paragraph chunking, the first paragraph scores high on `joy`; the second scores high on `sadness`. The emotion arc captures this shift. The scene-level aggregate is the mean of the stabilized per-chunk scores, which is more meaningful than the old single-vector approach.

**Arc stabilization layer** (mandatory):

The combination of 28 GoEmotions categories, multi-label output, and sliding windows produces noisy raw arcs. Without stabilization, the DSL compiler would receive chaotic emotion transitions (joy → neutral → sadness → surprise → anger within 5 sentences). Three mechanisms run in sequence via `smooth_emotion_arc()`:

1. **EMA smoothing** (`alpha=0.3`): Each chunk's scores are blended with the previous chunk to dampen single-chunk spikes while preserving genuine sustained shifts.
2. **Peak detection threshold** (`0.10` gap): A new dominant emotion is only assigned when the top score exceeds the runner-up by at least the threshold. Otherwise, the previous chunk's dominant emotion carries forward. This prevents noisy oscillation between closely-scored categories.
3. **Minimum segment duration** (`2` chunks): Segments shorter than the minimum are absorbed into the longest neighboring segment. This prevents single-chunk emotional "blips" from producing micro-transitions in audio output.

The stabilized arc replaces the raw arc — only stable data reaches the output.

**Schema and pipeline integration**: A new `EmotionArcEntry` model (`chunk_index`, `text_preview`, `dominant_emotion`, `scores`) was added to `schema.py`. The `SceneSignals` model gained an `emotion_arc` field (defaults to an empty list for backward compatibility). `pipeline.py` calls `compute_emotion_arc()` and includes the arc in the signals output.

**Remaining limitation**: The stabilization parameters (`alpha`, `peak_threshold`, `min_segment_chunks`) are hand-tuned defaults. Optimal values may vary by genre — a horror story benefits from faster emotional transitions than a literary drama. These parameters are exposed as keyword arguments on `compute_emotion_arc()` for future configurability.

### 4.3 ~~Low Discriminative Power of the Embedding Model~~ — **Fixed**

> **Status**: Resolved. The cosine-similarity anchor approach was replaced
> with a dedicated multi-label emotion classifier that outputs proper
> classification probabilities.

`all-MiniLM-L6-v2` was a 22M-parameter general-purpose sentence embedding model trained on semantic similarity, not emotion classification. The cosine-similarity-to-anchor approach produced scores where the top emotion barely exceeded the second (gap of ~0.005), making emotion assignment essentially random for scenes without extremely obvious emotional language.

**What changed — dedicated GoEmotions classifier**:

The entire approach was replaced. Instead of encoding text into a generic embedding space and comparing against hand-written anchor phrases, the engine now uses `SamLowe/roberta-base-go_emotions` — a multi-label classifier fine-tuned specifically on the GoEmotions dataset. This produces proper sigmoid probabilities per label, giving much higher discriminative power between emotion categories.

The `all-MiniLM-L6-v2` sentence-transformer model is **retained** inside `encode_text()` solely for the scene segmenter's semantic shift detection (`scene_segmenter.py`), which is unrelated to emotion classification.

**Performance mitigations**:

The classifier model (~500MB) is heavier than MiniLM (~80MB). Three mandatory mitigations keep latency within the ~1–1.5s per scene target:

1. **Batch inference** (`batch_size=16`): All chunks for a scene are classified in a single batched call, not one at a time.
2. **Singleton loading**: The classifier pipeline is loaded once and cached as a module-level singleton. Cold start (~2–3s) is amortized to zero after the first scene.
3. **Truncation** (`max_length=128`): Each chunk is a paragraph or 3-sentence window — no chunk needs 512 tokens.

**Remaining limitation**: The ~500MB model is the heaviest component. A future upgrade path is documented: `SamLowe/roberta-base-go_emotions-onnx` (INT8 quantized) provides the same 28 labels with 5× faster inference and 75% smaller footprint. The model name is stored in a configurable `_EMOTION_MODEL_NAME` constant for drop-in swapping. If a `distilroberta-go_emotions` variant with the full 28-label output appears on HuggingFace, it can also be swapped via this constant — the label integrity check at load time will verify compatibility.

---

## 5. ~~Heuristic Fallback Coarseness~~ (Resolved)

**Affected file**: `story_processing/ai/fallback_rules.py`

**Status**: Resolved. All three sub-problems have been addressed:

### 5.1 ~~Simplistic Energy Formula~~ → Multi-signal weighted sum

The energy formula now incorporates five factors instead of two:

- **Punctuation score** (retained, re-weighted)
- **Sentence-length variance** (retained, re-weighted)
- **Action verb density** — new `action_verb_density` signal computed in `structure_metrics.py` using ~50 high-energy verb lemmas matched via spaCy POS + lemma lookup
- **Arousal boost** — sum of emotion scores for high-arousal emotions (anxiety, anger, surprise, anticipation)
- **Pacing** — sentence count normalized to 0-1 (saturates at 15 sentences)

All weights are configurable via `HeuristicConfig`.

### 5.2 ~~Hard-Coded Scene Style Thresholds~~ → Configurable thresholds + weighted action score

- Dialogue thresholds (`narrative_heavy_max_dialogue`, `dialogue_driven_min_dialogue`) are now fields on `HeuristicConfig`, not magic numbers.
- `action_heavy` detection uses a **weighted composite action score** (streak + punctuation + verb density, each normalized to 0-1) instead of the old AND gate. A single signal spike cannot trigger `action_heavy` — the composite must cross a configurable threshold (default 0.45).
- Genre presets (`THRILLER_CONFIG`, `LITERARY_CONFIG`) are exported for future use, adjusting thresholds for genre-specific behavior.

### 5.3 ~~Three-Tier Confidence Scoring~~ → Continuous formula

Confidence is now a continuous value in the range [0.20, 0.85], computed from a weighted blend of:

- **Gap component**: how far the top emotion leads the second (normalized by `confidence_gap_scale`)
- **Absolute component**: how strong the top emotion score is on its own

This lets downstream consumers meaningfully distinguish "very sure heuristic" from "marginal guess".

---

## 6. ~~No Memory / Cross-Scene Context~~ (Resolved)

**Affected files**: `story_processing/pipeline.py`, `story_processing/context.py` (new), `story_processing/ai/classifier.py`, `story_processing/ai/fallback_rules.py`, `story_processing/ai/prompt_templates.py`

**Status**: Resolved. A new story context layer provides emotional arc continuity, global speaker reconciliation, pacing awareness, and deterministic scene IDs.

### 6.1 ~~Each Scene Is an Island~~ — **Fixed**

> **Status**: Resolved. A `StoryContextBuilder` now feeds rolling cross-scene
> context into the sequential classification step. Speaker reconciliation runs
> as a post-processing pass after parallel extraction.

The pipeline previously classified every scene in complete isolation — no scene ever saw data from any other scene.

**What changed — three cross-scene mechanisms in `context.py`**:

**A. Emotional Arc Continuity**:

A `StoryContextBuilder` maintains rolling state as scenes are classified sequentially. For each scene, it provides:

- The last 3 scenes' primary emotion labels.
- An **emotion trend** derived from mean arousal (sum of anxiety, anger, surprise, anticipation scores) over the last 3 scenes:
  - Monotonically increasing → `"escalating"`
  - Monotonically decreasing → `"de-escalating"`
  - Dominant emotion changes > 2 times in last 3 → `"volatile"`
  - Otherwise → `"stable"`

When the heuristic classifier sees that previous scenes share the same dominant emotion and the current scene's top two emotions are close (gap < 0.10), it applies a **momentum boost** (`*= 1.15`, re-normalized, clamped to [0, 1]) to the carried emotion. This prevents a single quiet paragraph from resetting a narrative buildup.

When the emotion trend is `"escalating"` and the scene is in the back half of the story (`position_ratio > 0.5`), energy gets a +1.0 bonus. Accelerating pacing adds another +0.5.

**Hard caps** prevent runaway drift: energy context shift is capped at +1.5 total per scene, and emotion score shift is capped at +0.15 per emotion per scene.

**B. Character Continuity (Speaker Reconciliation)**:

A `reconcile_speakers()` function runs after parallel extraction and before classification:

1. Builds a **global named-speaker registry** from all scenes (every non-`unknown_speaker_*` label).
2. For each `unknown_speaker_X`, checks if a named speaker from the registry appears in the **same sentence or 1–2 sentences prior** to the dialogue turn. If found, replaces the unknown label. (Tight proximity window only — wrong attribution is worse than unknown.)
3. **Globally renumbers** remaining unknowns with a single counter across all scenes, preventing ID collisions (scene 1's unknowns are `unknown_speaker_1`, `unknown_speaker_2`; scene 2's continue as `unknown_speaker_3`, etc.).

**C. Pacing Awareness**:

The builder tracks word counts per scene. Pacing trend is derived from the last 3 word counts:

- Scenes getting shorter → `"accelerating"` (faster pacing).
- Scenes getting longer → `"decelerating"` (slower pacing).
- Otherwise → `"steady"`.

The pacing trend feeds into energy adjustment (see above).

**LLM prompt integration**: When an LLM client is available and context exists, the classification prompt gains a summary-level `STORY CONTEXT` block (~5 lines: scene position, last 3 emotion labels, trend words, known character names). No raw score dicts or structure metrics are included — LLMs degrade with noise.

**Architecture note**: The `StoryContextBuilder` uses O(1) rolling state per scene (`get_context()` reads last 3 entries; `advance()` appends one entry). Total work across N scenes is O(N), not O(N²). No existing parallel performance is affected — the context layer sits between the parallel extraction step and the already-sequential classification step.

**Remaining limitations**:
- Emotion momentum is a simple heuristic — it cannot distinguish genuine narrative escalation from repetitive tone. The hard caps limit damage, but a more sophisticated approach would use the sub-scene emotion arc (from 4.2) for finer-grained trajectory analysis.
- Speaker reconciliation only resolves unknowns against names found in the text. Two scenes with `unknown_speaker_1` and `unknown_speaker_3` that are narratively the same character (but whose name never appears near the dialogue) will remain separate unknowns.
- Pacing trend uses word counts as a proxy for pace. A scene with many short sentences and a scene with few long sentences can have the same word count but very different perceived pacing. Sentence count or short-sentence-streak would be a more precise signal.

### 6.2 ~~Non-Deterministic Scene IDs~~ — **Fixed**

> **Status**: Resolved. Scene IDs now use a content-based SHA-256 hash
> instead of a random UUID.

```python
# Old (non-deterministic):
scene_id = f"scene_{span.scene_index:03d}_{uuid.uuid4().hex[:8]}"

# New (deterministic):
digest = hashlib.sha256(f"{scene_index}:{scene_text}".encode()).hexdigest()[:8]
scene_id = f"scene_{span.scene_index:03d}_{digest}"
```

The same story text now always produces the same scene IDs. Caching, comparison, and delta-tracking between runs are now possible. The `uuid` import has been removed from `pipeline.py`.

**Remaining limitation**: If the normalizer changes its output (e.g. whitespace handling), the hash input changes and all scene IDs shift. This is acceptable — a normalization change implies a meaningfully different pipeline run.

---

## 7. DSL Compiler Limitations

**Affected files**: `dsl/compiler.py`, `dsl/builders/clips.py`, `dsl/builders/settings.py`

### 7.1 No Timing Information in the Draft

The Draft Timeline deliberately omits `start`, `duration`, and `offset` fields — these are filled in by a downstream "Asset Resolver" that measures actual audio files. But this means:

- The Draft Timeline cannot be previewed or validated for temporal correctness.
- If the Asset Resolver is not yet built (which it currently isn't in this repo), the Draft Timeline is a blueprint that can't be executed.
- No estimated duration for the project, making it impossible to predict output length.

### 7.2 One Music Clip Per Scene

```python
def build_music_clips(scene, energy):
    # ... always returns exactly one clip
    clip = DraftClip(mood=mood, energy_hint=round(energy, 2), loop=True)
    return {"music": [clip]}
```

Every scene gets exactly one looping music clip. Real audio productions need:

- **Intro music** that plays before narration starts.
- **Transition stings** between emotional shifts within a scene.
- **Music swells** at dramatic moments.
- **Outro / fade-out** at scene end.

A 5-minute scene with a single looping mood tag feels monotonous in production.

### 7.3 silence_intent Is Underutilized

The pipeline computes `silence_intent` (none, short, medium, long) based on sentence density and short-sentence streaks. The DSL compiler uses it for exactly one thing: scene crossfade duration.

```python
SILENCE_TO_CROSSFADE = {"none": 1.0, "short": 1.0, "medium": 1.5, "long": 2.0}
```

It never generates:

- Explicit pause clips between dialogue turns (dramatic pauses are critical in audio drama).
- Silence before a scene's first narration (establishing the ambience).
- Extended silence after emotionally heavy dialogue (letting the moment breathe).

The signal is extracted but mostly wasted.

### 7.4 No Volume Automation

Music and ambience clips have static `gain` and optional `fade_in` / `fade_out` fields, but there is no mechanism for mid-clip volume changes. In a real audio drama:

- Music should duck (get quieter) during dialogue and swell between lines.
- Ambience should intensify at dramatic moments and fade during quiet introspection.
- SFX should punch through at specific narrative moments.

The ducking system handles some of this at the settings level, but it's a global rule, not per-moment automation.

---

## 8. Performance Concerns

**Affected files**: `story_processing/nlp/spacy_pipeline.py`, `story_processing/signals/semantic_metrics.py`, `story_processing/pipeline.py`

### 8.1 Heavy Model Loading

The pipeline loads three models on first run:

| Model | Purpose | Size | Load Time (typical) |
|---|---|---|---|
| `en_core_web_lg` (spaCy) | NLP parsing | ~560 MB | 5–15 seconds |
| `all-MiniLM-L6-v2` (sentence-transformers) | Semantic shift detection | ~80 MB | 2–5 seconds |
| `SamLowe/roberta-base-go_emotions` (transformers) | Emotion classification | ~500 MB | 2–3 seconds |

All three are loaded lazily (on first use) and cached as singletons, which is good. But there is no option to:

- Use a smaller spaCy model (`en_core_web_sm` is 12 MB and loads in <1 second).
- Disable semantic metrics entirely if emotion scoring isn't needed.
- Pre-load models before the pipeline starts (to move the latency out of the critical path).
- Use a quantized emotion classifier (`SamLowe/roberta-base-go_emotions-onnx` would be ~125 MB with 5× faster inference) — the model name is configurable via `_EMOTION_MODEL_NAME` but requires ONNX runtime dependencies not yet added.

For quick iteration during development, the 15-25 second cold start across all three models is painful.

### 8.2 Sequential LLM Calls

The pipeline classifies scenes sequentially (line 106 in `pipeline.py`):

```python
for scene_data in scene_data_list:
    raw_interp = classify(merged_signals, llm_client)
    # ... also calls extract_audio_cues() per scene
```

For a story with 20 scenes, this means 20 classification calls + 20 audio cue extraction calls = 40 sequential LLM round trips. At 1-3 seconds per call (for Gemini), that's 40-120 seconds spent waiting on the network — even though these calls are independent and could run in parallel.

### 8.3 No Incremental Processing

If you change one paragraph in a 10,000-word story, the entire pipeline re-runs from scratch: full spaCy parse, full emotion scoring, full LLM classification for every scene. There is no caching of intermediate results, no change detection, and no incremental update mechanism.

---

## 9. No Test Suite

**Affected**: the entire repository.

There are zero test files in the project. No `tests/` directory, no `pytest.ini`, no `conftest.py`, no test runner configuration.

**What this means in practice**:

- **Refactoring is risky**: Changing the dialogue extraction regex could silently break speaker attribution downstream. Without tests, you won't know until you manually run the pipeline and inspect the JSON output.
- **Regressions go unnoticed**: If a spaCy version update changes tokenization behavior, the sentence segmenter or speaker resolver could produce different results. No tests means no automated alarm.
- **Edge cases are untested**: The overlap resolver in dialogue extraction, the clamping logic in validation, the order-fixing in the DSL validator — all of these have subtle logic that should have unit tests covering boundary conditions.
- **Confidence in correctness is low**: Every module is "trust the developer" rather than "trust the test suite".

---

## 10. ~~No File Input / CLI Interface~~ (Resolved)

**Affected files**: `cli.py` (new), `pyproject.toml` (new), `main.py` (kept as legacy demo)

**Status**: Resolved. A proper `audstories` CLI with `process` and `batch` subcommands is now the primary entry point.

### 10.1 ~~Hardcoded Inline Story~~ — **Fixed**

> **Status**: Resolved. The CLI reads story text from files via `--input`.

The entry point previously had a hardcoded `SAMPLE_STORY` string in `main.py`. Processing a different story required editing source code.

**What changed — `audstories` console script**:

A new `cli.py` module at the project root implements a full CLI using `argparse` (stdlib — zero new dependencies). A `pyproject.toml` registers the `audstories` console script via `[project.scripts]`, making it available after `pip install -e .`.

**Supported commands**:

```
audstories process --input story.txt --output out/
audstories process --input story.txt --no-llm
audstories process --input story.txt --model gpt-4
audstories batch  --input ./stories/ --output ./out/
```

### 10.2 ~~No Output Path Specification~~ — **Fixed**

> **Status**: Resolved. `--output` controls where JSON files are written.

Output previously always went to `example_output.json` and `example_draft_timeline.json` in the project root.

**What changed**: The `--output` flag specifies the target directory. Two files are written:

- `{output_dir}/narrative_plan.json` (from the story-processing layer)
- `{output_dir}/draft_timeline.json` (from the DSL compiler)

For `process`, `--output` defaults to `.` (current directory). For `batch`, it defaults to `./out`, with each story getting a sub-directory named after its file stem (e.g. `out/scene1/narrative_plan.json`).

### 10.3 ~~No Model Selection~~ — **Fixed**

> **Status**: Resolved. `--model` selects the LLM backend by name prefix.

There was no way to choose an LLM backend from the command line.

**What changed**: A `--model` flag maps model names to the correct `LLMClient` subclass using a prefix heuristic:

| Model prefix | Backend | Example |
|---|---|---|
| `gpt-*`, `o1*`, `o3*`, `o4*` | `OpenAIClient` | `--model gpt-4` |
| `gemini*` | `GeminiClient` | `--model gemini-2.0-flash` (default) |
| anything else | `LocalLLMClient` (Ollama) | `--model qwen3:4b` |

`--no-llm` forces heuristic-only mode (mutually exclusive with `--model`).

### 10.4 ~~No Directory / Batch Processing~~ — **Fixed**

> **Status**: Resolved. `audstories batch` processes all `.txt` files in a directory.

**What changed**: The `batch` subcommand globs all `*.txt` files in the `--input` directory, processes each via a shared `run_single_file()` core function, and writes output to `{output}/{stem}/`. A summary is printed at the end showing how many files succeeded and failed.

### 10.5 Architecture Notes

**JSON boundary at IO surface**: The CLI calls `process_story_json()` and `compile_timeline_json()` — the JSON-bytes-returning variants — not the dict-returning versions. The CLI reads text in and writes JSON bytes out. The only internal deserialization is `orjson.loads()` for the handoff from narrative plan to the DSL compiler (which requires a dict input).

**Shared core, not nested CLI calls**: Both `cmd_process()` and `cmd_batch()` delegate to `run_single_file(input_path, output_dir, llm_client)`. The batch command never constructs fake `argparse.Namespace` objects or calls `cmd_process()`.

**Non-zero exit codes on failure**: Every error path — missing input file, LLM client initialization failure, processing exception — prints to stderr and returns exit code 1. Batch mode tracks per-file success/failure and exits non-zero if any file failed.

**Subparser-ready structure**: The parser uses `argparse` subparsers from day one. Adding future commands (`audstories estimate`, `audstories resolve`, `audstories render`) is a single function + subparser addition.

**Legacy `main.py`**: The original `main.py` is kept unchanged as a quick demo/test script. It is no longer the primary entry point.

**Remaining limitations**:
- No stdin reading — input must be a file path.
- No `--verbose` / `--quiet` logging control.
- No `--spacy-model` flag to override the default `en_core_web_lg`.
- No progress bar or estimated time remaining for long-running batch jobs.
- The `story/scene1.txt` sample file is now usable via `audstories process --input story/scene1.txt` but is not referenced by any automated test or default command.
