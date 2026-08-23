# How to Use Story-to-Script

A quick guide to get you up and running.

---

## 1 — Install

```bash
cd story-to-script

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
python -m spacy download en_core_web_lg
```

---

## 2 — Prepare Your Story

Create a plain `.txt` file with your story text. You can place it anywhere, e.g. `story/my_story.txt`.

---

## 3 — Run (Single File)

### Without an LLM (heuristic-only, no API key needed)

```bash
audstories process --input story/my_story.txt --output out/ --no-llm
```

### With Gemini (default)

Set your API key first:

```bash
set GEMINI_API_KEY=your-key-here        # Windows
# export GEMINI_API_KEY=your-key-here   # macOS / Linux
```

Then run:

```bash
audstories process --input story/my_story.txt --output out/
```

### With OpenAI

```bash
set OPENAI_API_KEY=sk-...
audstories process --input story/my_story.txt --output out/ --model gpt-4o-mini
```

---

## 4 — Run (Batch)

Process every `.txt` file in a folder at once:

```bash
audstories batch --input ./stories/ --output ./out/ --no-llm
```

Each story gets its own sub-folder inside `out/`.

---

## 5 — Check the Output

After a run you'll find two JSON files in the output folder:

| File | What it is |
|------|------------|
| `narrative_plan.json` | Scene-by-scene breakdown — structure, emotions, signals |
| `draft_timeline.json` | Audio-storytelling timeline compiled from the plan |

---

## Quick Python Usage

You can also use it directly in code:

```python
from story_processing.pipeline import process_story

story = open("story/my_story.txt").read()
plan = process_story(story)          # returns a dict
print(plan)
```

---

## Tips

- **No API key?** Just pass `--no-llm` — the engine uses built-in heuristic rules and still produces full output.
- **LLM fails?** The pipeline automatically falls back to heuristics, so you'll always get a result.
- **Want a quick demo?** Run `python main.py` — it processes a tiny built-in sample story and writes `example_output.json` + `example_draft_timeline.json`.
