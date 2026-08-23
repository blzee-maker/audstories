# Story-to-Script Engine

A deterministic NLP + controlled AI pipeline that transforms raw story text into a structured **Narrative Plan** — a scene-by-scene JSON representation of structure, signals, and emotional interpretation.

## Overview

The engine ingests plain-text stories and produces a rich JSON output describing every scene, including sentence structure, dialogue attribution, emotional tone, pacing signals, and classification labels. It is designed with a **deterministic-first** philosophy: every stage produces reproducible numeric facts, and AI classification is an optional, controlled layer on top.

```
Story Text → Preprocessing → NLP → Signals → Classification → Validation → Narrative Plan
```

## Features

- **Text Preprocessing** — Unicode normalization, smart-quote straightening, whitespace collapsing.
- **Scene Segmentation** — Automatic scene boundary detection via explicit markers (`Chapter`, `Scene`, `---`, `***`), triple-newline breaks, and temporal gap phrases.
- **Dialogue Extraction** — Regex-based extraction of double-quoted, single-quoted, and em-dash dialogue styles with overlap resolution.
- **Speaker Attribution** — Dependency-parse-based speaker resolution using spaCy; walks the parse tree to find subjects of speech verbs.
- **Structure Metrics** — Sentence length stats, punctuation scoring, dialogue ratio, short-sentence streak detection.
- **Semantic Metrics** — Embedding-based emotion similarity using `sentence-transformers` (all-MiniLM-L6-v2) with cosine similarity against six emotion anchors: *anxiety, joy, sadness, anger, calm, neutral*.
- **AI Classification** — Optional LLM-powered scene classification with retry logic and automatic heuristic fallback.
- **Heuristic Fallback** — Pure rule-based classification that works without any LLM, ensuring the pipeline always produces output.
- **Validation & Clamping** — Pydantic v2 schema enforcement plus logical consistency rules (e.g., low dialogue ratio cannot be classified as `dialogue_driven`).
- **Parallel Processing** — Per-scene structure and signal extraction runs in parallel via `ThreadPoolExecutor`.

## Installation

### Prerequisites

- Python 3.10+
- A spaCy English model (default: `en_core_web_lg`)

### Setup

```bash
# Clone and enter the project directory
cd story-to-script

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Download the spaCy model
python -m spacy download en_core_web_lg
```

### Dependencies

| Package                | Purpose                                   |
|------------------------|-------------------------------------------|
| `spacy >=3.7`          | NLP pipeline(tokenization, POS, dep parse)|
| `sentence-transformers >=2.2`| Embedding-based emotion scoring     |
| `pydantic >=2.5`       | Schema validation for the Narrative Plan  |
| `numpy >=1.26`         | Numeric computations                      |
| `orjson >=3.9`         | Fast JSON serialization                   |
| `httpx >=0.27`         | HTTP client for LLM backends              |

## Quick Start

Run the included example:

```bash
python main.py
```

This processes a short sample story using heuristic-only classification (no LLM required) and writes the Narrative Plan to `example_output.json`.

### Programmatic Usage

```python
from story_processing.pipeline import process_story, process_story_json

story = """
The power cut out, and in the sudden darkness, the old clock stopped ticking.

"I think the house just remembered what we did."
"""

# Get a Python dict
plan = process_story(story)

# Or get serialized JSON bytes
json_bytes = process_story_json(story)
```

### Using with an LLM

The pipeline supports optional LLM-powered classification via two built-in clients:

```python
from story_processing.ai.llm_client import LocalLLMClient, OpenAIClient
from story_processing.pipeline import process_story

# Ollama (local)
client = LocalLLMClient(base_url="http://localhost:11434", model="mistral")

# OpenAI-compatible API (OpenAI, vLLM, LM Studio, etc.)
client = OpenAIClient(api_key="sk-...", model="gpt-4o-mini")

plan = process_story(story, llm_client=client)
```

When an LLM client is provided the pipeline will:
1. Attempt LLM classification (temperature=0, JSON-only output).
2. Retry once on invalid JSON.
3. Fall back to heuristic classification if both attempts fail.

## Output Schema

The Narrative Plan follows a strict Pydantic-validated schema (`v1.0`):

```json
{
  "schema_version": "1.0",
  "scenes": [
    {
      "scene_id": "scene_000_fb65cd95",
      "structure": {
        "scene_id": "scene_000_fb65cd95",
        "sentence_count": 2,
        "word_count": 23,
        "sentences": ["..."],
        "dialogue_turns": [
          {
            "speaker": "unknown_speaker_1",
            "text": "I think the house just remembered what we did.",
            "start_char": 79,
            "end_char": 127
          }
        ],
        "speakers": ["unknown_speaker_1"]
      },
      "signals": {
        "avg_sentence_length": 11.5,
        "sentence_length_variance": 6.25,
        "short_sentence_streak": 0,
        "punctuation_score": 0.0,
        "dialogue_ratio": 0.391,
        "dialogue_turn_count": 1,
        "avg_dialogue_length": 9.0,
        "emotion_scores": {
          "anxiety": 0.1056,
          "joy": 0.0383,
          "sadness": 0.1005,
          "anger": 0.0485,
          "calm": 0.0357,
          "neutral": 0.0178
        }
      },
      "interpretation": {
        "primary_emotion": "anxiety",
        "energy_level": 4,
        "emotion_intensity": 1,
        "scene_style": "balanced",
        "silence_intent": "short",
        "confidence_score": 0.25
      }
    }
  ]
}
```

### Interpretation Fields

| Field               | Type    | Range / Values                                              |
|---------------------|---------|-------------------------------------------------------------|
| `primary_emotion`   | string  | `anxiety`, `joy`, `sadness`, `anger`, `calm`, `neutral`     |
| `energy_level`      | integer | 1–10                                                        |
| `emotion_intensity` | integer | 1–10                                                        |
| `scene_style`       | string  | `dialogue_driven`,`narrative_heavy`,`balanced`,`action_heavy`|
| `silence_intent`    | string  | `none`, `short`, `medium`, `long`                           |
| `confidence_score`  | float   | 0.0–1.0                                                     |

## Project Structure

```
story-to-script/
├── main.py                          # Example runner
├── requirements.txt                 # Python dependencies
├── example_output.json              # Sample output
├── story/                           # Sample story files
│   └── scene1.txt
└── story_processing/                # Core engine package
    ├── __init__.py
    ├── pipeline.py                  # End-to-end orchestrator
    ├── narrative_plan.py            # Final assembly & JSON serialization
    ├── preprocessing/
    │   └── normalizer.py            # Unicode & whitespace normalization
    ├── nlp/
    │   ├── spacy_pipeline.py        # Singleton spaCy model loader
    │   ├── scene_segmenter.py       # Heuristic scene boundary detection
    │   ├── dialogue_extractor.py    # Regex-based dialogue extraction
    │   └── speaker_resolver.py      # Dep-parse speaker attribution
    ├── signals/
    │   ├── structure_metrics.py     # Lexical, punctuation & dialogue signals
    │   └── semantic_metrics.py      # Embedding-based emotion scoring
    ├── ai/
    │   ├── classifier.py            # LLM classification with retry & fallback
    │   ├── llm_client.py            # Abstract + concrete LLM clients
    │   ├── prompt_templates.py      # Enum-constrained classification prompts
    │   └── fallback_rules.py        # Pure heuristic classification rules
    └── validation/
        ├── schema.py                # Pydantic v2 data models
        └── validator.py             # Logical consistency checks & clamping
```

## Architecture

The pipeline is split into clearly separated layers:

1. **Preprocessing** — Deterministic text normalization (Unicode NFKC, smart quotes, whitespace).
2. **NLP** — spaCy-powered tokenization, sentence splitting, POS tagging, and dependency parsing. Scene segmentation and dialogue extraction operate on the processed doc and raw text respectively.
3. **Signals** — Numeric fact extraction only. Structure metrics (sentence lengths, punctuation scores, dialogue ratios) and semantic metrics (embedding cosine similarity against emotion anchors).
4. **Classification** — Controlled AI layer. Attempts LLM classification with strict JSON constraints, retries once on failure, and falls back to deterministic heuristic rules.
5. **Validation** — Pydantic schema enforcement plus business-rule clamping (e.g., energy levels are capped when sentence length is high).
6. **Assembly** — Combines all per-scene data into the final Narrative Plan and serializes to JSON via `orjson`.

## License

This project is part of the PCDDJ Engine.
