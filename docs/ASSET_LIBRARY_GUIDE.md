# Building the AudStories audio library

Welcome. This is your job description, your spec, and your acceptance criteria in one
file. Read it once end to end before you buy or record anything — a few of the rules here
look arbitrary until you understand how the engine picks a sound, and Section 2 explains
that.

**Your mission:** a curated library of sound effects, ambience and music that lets
AudStories turn a story into a produced audio drama *without a human choosing each sound*.
The measure of success is not how many files you gather. It is **how often the engine
picks the right one on its own.**

---

## 1. What the product does, in one minute

A user pastes a story. Stage 1 analyses it and emits a list of **asset requirements** —
one per sound the piece needs. Each requirement carries a short text **descriptor** such
as:

- music → `tension_mid`, `hopeful`, with an energy hint from 0 to 1
- ambience → `park daytime`, `rain on window`
- sfx → `footsteps running`, `door slam`

Then the engine looks in the library for a file that matches that descriptor, and Stage 2
renders everything into a finished mix.

**You are building the thing it searches.** When it finds nothing, the user has to go find
a sound themselves, and the product has failed at the job it promises to do.

---

## 2. How the engine picks a file — read this before anything else

This is the part that decides how you name and tag every file. There are three separate
matching paths, and they behave differently.

### 2.1 Sound effects and ambience: words in the filename

The matcher tokenises the descriptor and the filename, then counts the words they share
([`clap_index.py:48-62`](../backend/asset_engine/src/asset_engine/resolvers/clap_index.py#L48-L62)).
The score is:

```
score = (number of shared words) / (number of words in the query)
```

and a file is only used if it scores **0.45 or higher**
([`library_resolver.py:46`](../backend/asset_engine/src/asset_engine/resolvers/library_resolver.py#L46)).

The query is built by joining the descriptor, semantic role, mood, atmosphere and SFX hint
together. So a query can be several words long, and a file matching only one of them will
fall below the threshold and be ignored.

There is no understanding of meaning here. **No synonyms, no plurals, no spelling
tolerance.** These all fail to match `door slam`:

| Filename | Why it fails |
|---|---|
| `Door_Slams_01.wav` | "slams" ≠ "slam" |
| `heavy_wooden_entrance_bang.wav` | no shared words at all |
| `SFX_0042_final_v3.wav` | no words the engine can use |

And this one succeeds: `door_slam_wood_heavy_01.wav`.

> **Consequence:** the filename *is* the search index. Extra descriptive words in the name
> cost nothing and can only help, as long as they're words a story would actually use.

The index is built from your filenames by a command (Section 7.3), which turns
`door_slam_wood_heavy_01.wav` into the tag string "door slam wood heavy 01"
([`clap_index.py:85`](../backend/asset_engine/src/asset_engine/resolvers/clap_index.py#L85)).
Nothing else about the file is read. Not ID3 tags, not folder names, not a spreadsheet.

### 2.2 Music: a catalog file with structured tags

Music is different and better. It is matched from `music_catalog.json`, where each track
carries real fields ([`music_catalog.py:24-32`](../backend/asset_engine/src/asset_engine/resolvers/music_catalog.py#L24-L32)).
The scoring
([`music_catalog.py:171-200`](../backend/asset_engine/src/asset_engine/resolvers/music_catalog.py#L171-L200))
works out like this:

| What matches | Points | Notes |
|---|---|---|
| `role` | **hard filter** | Wrong role = the track is never even considered |
| `emotion` overlap | up to **0.40** | The single biggest contributor |
| `tags` + `genre` overlap | up to 0.25 | 0.05 per matching word |
| `energy` closeness | up to 0.25 | Needs `energy` set on the track |
| `loopable`, for underscore | 0.20 | Only when the requirement wants a loop |

A track still needs **0.45 to be used**. Do the arithmetic and two rules fall out, both of
which you must follow:

1. **Every music track needs `emotion` tags.** Tags and genre alone max out at 0.25, which
   is below the threshold. A track with no emotion tags will essentially never be picked.
2. **Every music track needs an `energy` value.** Without it you lose a quarter of the
   available score.

The three roles are fixed: **`underscore`** (plays under dialogue, should loop),
**`stinger`** (a short hit of 2–6 seconds for a reveal or scene end), and **`theme`** (a
recurring identity piece). A role outside that set makes the catalog fail to load.

### 2.3 The order the engine tries things

From [`library_resolver.py:247-300`](../backend/asset_engine/src/asset_engine/resolvers/library_resolver.py#L247-L300):

1. **Music only:** the music catalog.
2. **Everything:** the project's own slot folder — a file the user dropped in by hand.
3. **SFX and ambience:** the shared library index (Section 2.1).
4. **Last resort:** a Freesound download, if enabled.

Step 4 is why your work matters. Freesound fallback takes **the top text hit without
anyone listening to it**, downloads a lossy preview copy, and accepts licences that
legally require a credit line
([`freesound_client.py:26-72`](../backend/asset_engine/src/asset_engine/resolvers/freesound_client.py#L26-L72)).
It is a prototype crutch. Every slot your library fills properly is a slot that doesn't
fall through to a random internet file.

---

## 3. The vocabulary rule — the single most important rule in this document

Because matching is word-for-word, the library and the story analysis must **use the same
words**. If Stage 1 writes `downpour` and your file says `heavy_rain`, the right sound is
sitting in the library and will never be found.

So the project keeps **one controlled vocabulary**, and it is the backbone of your work.

**Your first deliverable is that vocabulary file** (Section 6, Phase 0). Once it exists:

- Every filename is built only from words in it.
- Om wires the same list into the Stage 1 prompt so the model describes sounds in your
  words.

When you need a word that isn't in the list, **add it to the list first**, then use it.
Never invent vocabulary file by file. A vocabulary that drifts is the same as no
vocabulary.

### Choosing the words

Prefer the plain word a writer would use. For each concept pick **one** form and stick to
it forever:

| Use | Not |
|---|---|
| `footsteps` | `footstep`, `steps`, `walking` |
| `rain` | `downpour`, `rainfall`, `precipitation` |
| `door` | `doorway`, `entrance` |
| `night` | `nighttime`, `evening`, `dark` |

Singular or plural, British or American — it does not matter which you choose. It matters
enormously that you choose once.

---

## 4. Naming and tagging

### 4.1 Filenames (SFX and ambience)

```
<subject>_<action-or-qualifier>_<material-or-place>_<variant>.wav

footsteps_walk_wood_01.wav
footsteps_run_gravel_03.wav
door_slam_wood_heavy_01.wav
door_creak_open_slow_02.wav
rain_heavy_window_indoor_01.wav
market_crowd_day_india_02.wav
```

Rules:

- **Lower case, words separated by underscores.** No spaces, no capitals, no hyphens.
- **Words from the vocabulary only.**
- **Most important word first**, since that's the one most likely to be in the descriptor.
- **Two-digit variant number at the end**, always, even for the first one.
- **No version words, dates or initials.** `_final`, `_v2`, `_mix3`, `_JS` are noise that
  dilutes the score — remember the denominator is the number of query words, so junk words
  in the *name* don't hurt directly, but they signal a file that was never cleaned up.
- **3 to 6 meaningful words.** One word is too vague to reach the threshold on a long
  query; ten words is a file that matches everything badly.

### 4.2 The music catalog

`music_catalog.json` lives at the library root and looks like this:

```json
{
  "tracks": [
    {
      "path": "music/tension_underscore_strings_low_01.wav",
      "role": "underscore",
      "emotion": ["tense", "anxious", "uneasy"],
      "genre": ["orchestral", "strings"],
      "tags": ["pulse", "sustained", "dark"],
      "energy": 0.35,
      "duration_s": 124.0,
      "loopable": true
    }
  ]
}
```

- `path` is **relative to the library root**, using forward slashes.
- `emotion` — 2 to 4 words. Required, per Section 2.2. Include the near-synonyms a story
  might use; this is the one field where synonyms earn their keep.
- `energy` — 0.0 to 1.0. Required. Roughly: 0.1 barely moving, 0.4 steady, 0.7 driving,
  0.9 frantic.
- `loopable` — `true` only if you have actually looped it and heard no seam.
- Validate every edit with `asset-engine library validate-music` (Section 7.3). A malformed
  catalog stops the whole pipeline, so never commit one you haven't validated.

---

## 5. Quality standard

Anything that fails these is rejected. No exceptions, no "we'll fix it later" — a bad file
in the library is worse than a missing one, because a missing one falls through to a
fallback while a bad one gets confidently placed in someone's finished episode.

### 5.1 Technical

| Rule | Standard | Why |
|---|---|---|
| Format | WAV, 48 kHz, 24-bit (44.1 kHz accepted). **Never MP3 as a source** | The engine re-processes and re-exports; lossy damage compounds at each step |
| Channels | SFX **mono**; ambience and music **stereo** | Mono effects can be placed anywhere in the stereo field; ambience needs width |
| SFX recording | **Dry** — no reverb, no echo, no room character | The scene decides the room. A bathroom-sounding door in a forest gives the trick away |
| Start of file | Trimmed so the sound starts at the first attack, within ~10 ms | Effects get anchored to a spoken line; leading silence lands them late |
| End of file | Clean decay, short fade, no click | Clicks are obvious in a quiet mix |
| Noise floor | Below −60 dBFS on SFX. No hiss, hum, or handling noise | Noise from six layers adds up into audible mud |
| Ambience length | **60 seconds minimum**, seamlessly loopable | Short loops repeat obviously across a three-minute scene |
| Loudness | Consistent within each category | The mixer's defaults then work without per-file fixing |
| Duration (SFX) | Typically under 5 seconds unless the sound is genuinely long | |

### 5.2 Content

- **No intelligible speech in ambience.** A clear English sentence behind a Hindi scene
  destroys the illusion. Indistinct crowd murmur is fine and often necessary.
- **No music inside an ambience file** — a radio in a café recording will clash with the
  score.
- **Nothing recognisable as a real brand or person:** a well-known ringtone, a famous
  jingle, a recognisable voice.
- **One file, one job.** A recording of "rainy street with a passing car and a barking dog"
  cannot be controlled. Rain, car and dog go in three files.
- **Variants must be genuinely different takes**, not the same take pitch-shifted. The
  point is to avoid the machine-gun effect of one footstep repeating.

### 5.3 Licensing — the rule you cannot get wrong

Our users **sell** what they make. A licence that doesn't allow that is a legal problem for
them and for us.

| Status | What it covers |
|---|---|
| ✅ **Allowed** | CC0 / public domain; sounds you recorded yourself for this project; paid libraries whose licence explicitly permits redistribution **to our end users** in a product |
| ⚠️ **Only with approval** | CC-BY. It works legally but every export must carry a credit line, and we don't have that mechanism built yet. Ask Om before using any |
| ❌ **Never** | CC-BY-NC or any "non-commercial only" licence; anything ripped from YouTube, a film, a game, or another product; anything whose licence you cannot produce a copy of |

**The trap to watch for:** many paid stock libraries license the sound to *the buyer* for
*their own* productions. That does not cover us shipping it inside a product for thousands
of other people to use. Read the actual licence text on redistribution before any purchase,
and if a clause is ambiguous, assume it's a no and ask Om.

**For every single file, record:** source, URL or invoice, licence name, a saved copy of
the licence text, the date, and whether attribution is required. No record, no shipping.
This tracking is not bureaucracy — it is what will later let us put a licence sheet in
every export, which is a real selling point for the product.

---

## 6. The plan, in phases

### Phase 0 — Measure before you collect (first week)

Do not start buying sounds. Start by finding out what the engine actually asks for.

1. Get the project running (Section 7.1).
2. Take **30 to 50 stories** in our target genre — ask Om which, most likely serialised
   drama, possibly Hindi.
3. Run Stage 1 on each and collect every `mood`, `atmosphere` and `sfx_hint` it produces.
4. Put them all in one sheet, group the ones that mean the same thing, and **count them**.

You will find the counts drop off steeply: a few dozen concepts cover the large majority of
requests. That list, in frequency order, is your shopping list — and the grouped words
become the first version of the vocabulary file.

**Deliverables:** `docs/asset-vocabulary.md` (the controlled vocabulary), and the frequency
sheet showing how you derived it.

### Phase 1 — The core set (~300–500 files)

Work strictly in frequency order from Phase 0. The split below is a starting estimate;
let your own counts correct it.

**Ambience, ~80–120 files**

- Indoors: home day, home night, kitchen, office, hospital, classroom, café, car interior,
  train interior, small hall
- Outdoors: city street day, city street night, quiet residential, village, forest day,
  forest night, beach, park, highway
- Weather: light rain, heavy rain, rain heard from indoors, storm, wind
- If we go Indian-language first: bazaar, temple courtyard, monsoon, auto-rickshaw traffic,
  local train platform, village with cattle and birds, wedding crowd
- **2 to 3 variants of each**, so twenty night-time scenes don't all use one file

**Sound effects, ~200–300 files**

- **Footsteps first — the largest category by far.** Each surface (wood, concrete, gravel,
  grass, tile, stairs) × each pace (walk, run, creep) × **3 to 5 takes each**
- Doors: open, close, slam, knock, creak, lock, for both a house door and a car door
- Body and cloth: rustle, sit, stand, fall, hug
- Objects: phone ring, phone vibrate, keys, glass, cup on table, paper, zip, light switch
- Genre packs (action, horror, sci-fi) come **later**, and only if the Phase 0 counts
  demand them

**Music, ~60–100 tracks**

- Across the three roles (`underscore`, `stinger`, `theme`)
- Across emotions: tense, sad, romantic, wonder, joyful, fearful, triumphant, mysterious
- Across energy: low, mid, high
- Underscore must loop and must be plain enough to sit under dialogue without fighting it
- Stems (drums, pads, melody as separate files) are a bonus worth paying for

### Phase 2 — Close the gaps with real data

Once the product is running, unresolved requirements get logged. **That log is your backlog
from then on.** Work it in frequency order. The library should grow from things users
actually asked for and didn't get — never from guesses.

---

## 7. Working with the repo

### 7.1 Setup

```powershell
.\setup.ps1              # Windows
```

```bash
./setup.sh               # macOS / Linux
```

You need Python 3.13+, Node 18+ and FFmpeg on PATH. Then confirm the install works with no
API keys at all:

```bash
python examples/render_demo.py
```

Full instructions are in [SETUP.md](../SETUP.md), and
[CONTRIBUTING.md](../CONTRIBUTING.md) covers the repo's conventions.

### 7.2 Where the library lives

Two different things, easy to confuse:

- **The shared library** — what you are building. One folder tree, `music/`, `ambience/`,
  `sfx/` at its root, plus `music_catalog.json` and a generated `index/` folder. It lives
  outside the repo; ask Om where the team copy is kept.
- **A project slot folder** — created per project by the pipeline, one folder per required
  sound, where a *user* drops their own file. See
  [examples/asset-library/README.md](../examples/asset-library/README.md). You don't
  maintain these; they just explain the layout you'll see when testing.

### 7.3 The commands you'll use

```bash
# Rebuild the search index after adding or renaming SFX or ambience — REQUIRED,
# new files are invisible until you do this
asset-engine library index --kind sfx      --audio-library <library-root>
asset-engine library index --kind ambience --audio-library <library-root>

# Check the music catalog parses before you commit it
asset-engine library validate-music --music-catalog <library-root>/music_catalog.json

# See which slots a project still can't fill
asset-engine status --draft <draft_timeline.json> --library <project-assets>

# Resolve a project against the shared library and see what matched
asset-engine resolve --draft <draft_timeline.json> --library <project-assets> \
  --out <out-dir> --audio-library <library-root> \
  --music-catalog <library-root>/music_catalog.json --use-clap --dry-run
```

The index writes to `<library-root>/index/<kind>_index.json`. **Rebuilding it is not
optional** — the resolver reads that file, not the folder, so a file you added ten minutes
ago does not exist until the index is rebuilt.

### 7.4 Never commit audio

`.gitignore` excludes audio deliberately, and [CREDITS.md](../CREDITS.md) explains why: no
third-party media is redistributed in this repository. If a file ever genuinely needs to be
committed, it takes both a gitignore negation **and** a CREDITS.md row — and a conversation
with Om first.

What you *do* commit: the vocabulary file, `music_catalog.json`, your tracking sheet, and
any notes or scripts.

---

## 8. Quality control: how a file gets accepted

Run this on every batch. Batches of 20 to 40 work well.

**Step 1 — Technical check.** Format, sample rate, channels, noise floor, trimmed start,
clean end, loop seam for ambience. Ask Om for the validator script if it exists yet; if it
doesn't, request it — it's a small piece of work that saves you hours every week.

**Step 2 — Listen in context, not in isolation.** This is the step people skip and it's the
one that matters. Put the sound in a test scene, under dialogue, with ambience playing, at
normal listening volume. Sounds that are lovely on their own routinely fall apart in a mix.

**Step 3 — Grade it.**

- **A** — ship it in the library
- **B** — usable, but only as a fallback; note why it isn't an A
- **Reject** — delete it, and record what was wrong so you don't buy it again

**The bar:** a listener should notice *the scene*, not *the sound*. Anything that makes
someone think "that's a sound effect" is not an A.

**Step 4 — Matching check.** Write down the descriptor a story would plausibly produce for
this sound, then confirm the engine actually finds the file for it. Rebuild the index and
run a resolve to see it happen. **A file the engine can't find does not count as done**,
however good it sounds.

**Step 5 — Record it** in the tracking sheet, with the licence details from Section 5.3.

### The tracking sheet

One row per file: `filename`, `category`, `duration`, `source`, `licence`,
`attribution_required` (yes/no), `commercial_ok` (yes/no), `date_added`, `grade` (A/B),
`notes`. Keep it in the repo as CSV so it can be diffed and, later, read by code.

---

## 9. What "done" looks like for each batch

A batch is finished when all of these are true:

- [ ] Every file passes the technical spec in 5.1
- [ ] Every file passes the content rules in 5.2
- [ ] Every filename uses only vocabulary words, in the pattern from 4.1
- [ ] Licence recorded, licence text saved, commercial use confirmed
- [ ] Music tracks have `emotion`, `energy` and a validated catalog entry
- [ ] The index has been rebuilt
- [ ] You ran a resolve and **saw the engine pick these files** for realistic descriptors
- [ ] The tracking sheet is updated
- [ ] Nothing audio was committed to git

---

## 10. How we'll work together

**Weekly:** a short note with how many files were added by category, what percentage of a
test story's requirements now resolve, which descriptors still fail, and what you want to
buy next.

**The number that matters** is not the file count. It is the **resolution rate**: of all
the requirements a real story generates, what share does the engine fill by itself? Track
it every week on the same set of test stories, and watch the line go up. That single number
is the honest measure of whether the library is working.

**Ask before deciding these — they're not yours to call alone:**

- Any purchase, and any licence clause you're unsure about
- The target language and genre, if it isn't already settled
- Adding a word to the vocabulary that overlaps something already in it
- Anything that needs a code change; write it up and send it to Om rather than editing the
  engine

**Good things to ask for:** the technical validator script, a sidecar tag file so a sound
can carry synonyms its filename doesn't (right now the index is built from filenames
alone), and the unresolved-requirements log as soon as there's traffic to log.

---

## 11. The short version

If you remember five things:

1. **The filename is the search index.** Name files in the words a story would use.
2. **One vocabulary, used everywhere.** Build it first, from real data, and never drift.
3. **Music needs emotion tags and an energy value**, or it will never be chosen.
4. **Rebuild the index**, or your work is invisible.
5. **Judge sounds in a mix, not alone** — and never ship a licence you can't produce.
