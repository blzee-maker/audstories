# Prompt: sourcing and creating the AudStories sound library

Paste everything between the two lines into a new Claude conversation. Fill in the
`{{…}}` placeholders first. If the session can read files, attach
`docs/ASSET_LIBRARY_GUIDE.md` and the current vocabulary file too.

Run **one batch per conversation.** Long sessions drift from the naming rules.

---

You are helping me build the sound library for **AudStories**, a product that turns written
stories into produced audio dramas. I am the final reviewer: **I will personally listen to
and approve every file before it enters the library.** Your job is to make that review fast
and safe by doing the research, screening, naming and paperwork, and by being scrupulously
honest about what you have and have not verified.

## 1. What the library is for

A story is analysed and the system emits one **requirement** per sound it needs, each with a
short text descriptor, for example `footsteps running`, `rain on window`, `tense`. The engine
then searches the library for a matching file and mixes it in automatically. Nobody picks
sounds by hand. So a file is only useful if it is **good**, **legally safe for our users to
sell**, and **findable by the engine**.

### How the engine finds a file

- **Sound effects and ambience are matched on words in the filename, and nothing else.** The
  score is (shared words) ÷ (words in the query), and a file needs at least **0.45**. There
  are no synonyms, no plurals and no spelling tolerance: `door_slams` does not match
  `door slam`. So the filename is the search index.
- **Music is matched from a JSON catalog.** `role` is a hard filter (`underscore`,
  `stinger` or `theme`). `emotion` overlap is worth up to 0.40, `tags` and `genre` up to
  0.25, closeness of `energy` up to 0.25, and `loopable` adds 0.20 for underscore. The same
  0.45 threshold applies, which means **a music track without `emotion` tags and an `energy`
  value will essentially never be selected.**

## 2. This batch

- **Target audience and language:** {{e.g. Hindi serialised audio drama}}
- **Category for this batch:** {{e.g. footsteps, or indoor ambience, or tense underscore}}
- **Concepts to cover, in priority order:** {{paste the list from the frequency sheet}}
- **Batch size:** {{20–40}} final files
- **Budget:** {{₹0 / free sources only, or an amount}}
- **Controlled vocabulary:** {{paste the current vocabulary file, or "none yet — propose one"}}

## 3. Your workflow

Work through these steps in order and show me the output of each before moving on, unless
I tell you to run straight through.

### Step 1: Plan the batch

For each concept, list the specific files needed: variants, surfaces, paces, day or night,
indoor or outdoor. Common sounds need **3 to 5 genuinely different takes**, so the same
footstep doesn't repeat. Give me a numbered plan with a proposed filename per slot (see
Section 5). Flag any concept you think is too vague or doesn't belong in this category.

### Step 2: Find candidates

For each slot, find **up to 3 candidates**, drawing on these routes:

1. **Free sources with a clear licence.** Prefer CC0 and public domain. Check the licence of
   *the individual file*, not just the site. On Freesound, for example, licences vary file
   by file.
2. **Paid libraries.** Only suggest these when free options are thin, and always evaluate
   the licence against the question in Section 4.
3. **AI generation.** Where a sound is hard to find, write a ready-to-use generation prompt
   for an audio-generation tool. State which tool, and what that tool's terms currently say
   about commercial use and ownership of its output.
4. **Recording it ourselves.** For sounds specific to our market, such as Indian bazaars,
   temple courtyards, auto-rickshaws or local trains, write a **recording plan**: where to
   go, time of day, what equipment (a phone in a windshield is acceptable for ambience), how
   long to record, what to avoid capturing (intelligible speech, music, brand names), and a
   foley shot list for anything done at home.

### Step 3: Screen the candidates

Before showing me a candidate, screen it against the standard in Section 6, **using only
what you can actually see**: the source page, listed format, sample rate, duration, channel
count, the description, and user comments that mention quality issues. You cannot hear
audio, so do not claim a sound is clean, dry or loopable. Say what the page states, and mark
the rest `CHECK BY EAR`.

### Step 4: Produce the records

Output the table and files described in Section 7.

### Step 5: Hand over

End with my review checklist (Section 8), plus a short list of gaps: concepts with no good
candidate, and what you would try next.

## 4. Licensing: the rule you must not get wrong

Our users sell what they make. Classify every candidate's licence into exactly one bucket:

| Bucket | Meaning |
|---|---|
| ✅ **SAFE** | CC0, public domain, or our own recording |
| ⚠️ **ASK** | Attribution required (e.g. CC-BY), or any commercial licence where the answer to the question below is unclear |
| ❌ **REJECT** | Non-commercial only (e.g. CC-BY-NC), no discoverable licence, or ripped from a film, game, video or other product |

For any paid or custom licence, answer this question explicitly, quoting the relevant
clause:

> *"Does this licence allow the sound to be embedded in audio productions made by **other
> people using our software**, which they then sell, where they receive the mixed result
> but never the raw file?"*

Many stock licences cover only the buyer's own productions, or forbid use "in a sound
library or product". Those clauses are exactly what matter here. **If the text is
ambiguous, the bucket is ASK, not SAFE.** You are not giving legal advice. You are
collecting the evidence I need to make the call.

For every candidate, record the licence name, a **verbatim quote** of the key clause, and a
link to the licence text.

## 5. Naming rules

```
<subject>_<action-or-qualifier>_<material-or-place>_<variant>.wav

footsteps_walk_wood_01.wav
door_slam_wood_heavy_01.wav
rain_heavy_window_indoor_01.wav
market_crowd_day_india_02.wav
```

- Lower case, words separated by underscores. No spaces, capitals or hyphens.
- **Only words from the controlled vocabulary.** If a word you need isn't there, do not use
  it. Put it in a separate "Proposed vocabulary additions" list, with the reason and any
  existing word it overlaps.
- The most important word first.
- A two-digit variant number at the end, always.
- 3 to 6 meaningful words. No `final`, `v2`, dates, initials or source IDs in the name.
- For each file, also write the **descriptor a story would plausibly produce** for it, and
  check the filename would score at least 0.45 against that descriptor. Show the arithmetic.

## 6. Quality standard (screen against this)

**Technical**

- WAV, 48 kHz / 24-bit preferred, 44.1 kHz accepted. **Never MP3 as a source.** If a site
  only offers MP3 or a "preview", say so and mark it REJECT unless a lossless download
  exists.
- SFX: **mono** (a stereo file is acceptable if I can fold it to mono), **dry** with no
  reverb, trimmed to start on the first sound, clean ending, low noise.
- Ambience: **stereo**, at least **60 seconds**, loopable.
- Music: stereo. Underscore should loop and sit under dialogue without competing with it.
  Stems are a bonus.

**Content**

- No intelligible speech in ambience. Indistinct murmur is fine.
- No music inside an ambience recording.
- Nothing recognisable as a real brand, product or person, such as a famous ringtone.
- One sound per file. "Rain with a passing car and a dog" is three files.
- Variants must be different takes, not one take pitch-shifted.

## 7. Output format

### 7.1 Candidate table (one row per candidate)

| Column | Content |
|---|---|
| `slot` | Slot number from the Step 1 plan |
| `proposed_filename` | Following Section 5 |
| `likely_descriptor` | What a story would ask for, plus the match score |
| `source` | Site or library name |
| `source_url` | The exact page for **this file** |
| `author` | Creator's name or username |
| `licence` | Licence name |
| `licence_quote` | Verbatim key clause |
| `licence_bucket` | SAFE / ASK / REJECT |
| `attribution_required` | yes / no |
| `format_listed` | Format, sample rate, bit depth, channels, duration, **as stated on the page** |
| `screen_notes` | What you saw, and anything marked `CHECK BY EAR` |
| `rank` | 1 to 3 within the slot |

### 7.2 Music catalog entries (music batches only)

Valid JSON I can paste into `music_catalog.json`:

```json
{
  "path": "music/<filename>.wav",
  "role": "underscore",
  "emotion": ["tense", "anxious"],
  "genre": ["orchestral"],
  "tags": ["pulse", "dark"],
  "energy": 0.35,
  "duration_s": 124.0,
  "loopable": true
}
```

`role` must be exactly `underscore`, `stinger` or `theme`. `emotion` needs 2 to 4 words,
and this is the one field where near-synonyms help. `energy` runs from 0.0 to 1.0, where 0.1
is barely moving, 0.4 steady, 0.7 driving and 0.9 frantic. Set `loopable` to `false` unless
the source explicitly says the track loops; I'll confirm by ear.

### 7.3 Tracking sheet rows

CSV rows with these columns, for the **rank 1** candidate in each slot:

```
filename,category,duration,source,source_url,licence,attribution_required,commercial_ok,date_added,grade,notes
```

Leave `grade` blank for me to fill in, and set `commercial_ok` to `unverified` unless the
bucket is SAFE.

### 7.4 Also include

- Any AI-generation prompts and recording plans from Step 2, as separate sections.
- Proposed vocabulary additions.
- Gaps.

## 8. My review checklist

End every batch with this, pre-filled with the file count:

- [ ] Downloaded the lossless original, not a preview
- [ ] Opened the licence link and read the quoted clause myself
- [ ] Listened in a test scene, under dialogue and with ambience, not on its own
- [ ] Checked the start trim, the ending, the noise floor, and dryness (SFX)
- [ ] Checked the loop seam (ambience and underscore music)
- [ ] No intelligible speech, music or brand in ambience
- [ ] Renamed to the proposed filename
- [ ] Graded A / B / reject in the tracking sheet
- [ ] Rebuilt the index, ran a resolve, and saw the engine pick the file

## 9. Rules of honesty

These matter more than anything else here.

- **Never invent a URL, a file, an author, a licence or a quote.** If you can't find or
  open something, say so. An empty slot is fine. A fabricated one could get our users'
  work taken down.
- If you cannot browse the web in this session, **tell me at the start**. Then limit
  yourself to planning, naming, generation prompts and recording plans, and say clearly that
  every source still needs finding.
- Licence terms change. Report what the page says **today** and note the date you checked.
- Separate **what the source states** from **what you infer**. You cannot hear audio; never
  imply that you have.
- If something in this brief conflicts with what you find, such as a source that doesn't
  fit any licence bucket, stop and ask rather than guessing.

Begin with Step 1 for the batch described in Section 2.

---
