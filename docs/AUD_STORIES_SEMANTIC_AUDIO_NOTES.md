# Aud-Stories / CLAP Semantic Audio — Assessment & Impact on Deployment Requirements

*Companion note to `DEPLOYMENT_REQUIREMENTS.md` for the PCDDJ platform.*

---

## 1. Executive summary

The proposal is **sound and well-aligned** with fixing the brittle folder-name / token-overlap resolver. Replacing `catalog.find_best()`-style logic with **CLAP text ↔ audio embeddings + FAISS** is a standard, defensible architecture. Treating **Freesound as a licensed, attribution-aware fallback** is the right pattern, but **commercial Freesound API use must be settled before launch** (as the spec states).

**Recommended stance:** Ship **Phase 1 (local CLAP + FAISS only)** first; it already beats filename matching and avoids API, legal, and network complexity. Add Freesound in a later phase once attribution and licensing are wired into `asset_manifest.json` and your product terms.

---

## 2. Technical opinion

### Strengths

- **Semantic gap:** CLAP directly addresses the failure mode where descriptors are natural language and library files are arbitrary names.
- **FAISS:** Appropriate for fast top-K search; `IndexFlatIP` + L2-normalized vectors for cosine similarity matches common practice.
- **Re-rank Freesound previews with CLAP:** Important; keyword search alone is weak for “sounds like” intent.
- **Incremental index updates:** Keeps ops sane as the library grows.
- **Honest limitations section:** Music/mood weakness and variable Freesound quality are real; planning a separate path for music later is reasonable.

### Risks and caveats

- **RAM:** CLAP (e.g. ~900 MB weights) loads **in addition to** Engine 1’s stack (spaCy, sentence-transformers, transformers — already **~1.5–3 GB per active worker** in `DEPLOYMENT_REQUIREMENTS.md`). Per-worker memory headroom must be recalculated if CLAP runs **inside the same Celery worker process** as Stage 2.
- **GPU vs CPU:** Spec uses `use_cuda=False`. Acceptable for low concurrency; under load, consider a dedicated worker profile or GPU only if profiling shows resolve time dominates.
- **Index build time:** First full rebuild for large libraries should be a **background job** (as noted), not blocking `run-stage2`.
- **Freesound:** **CC0/CC-BY filtering is mandatory**; **commercial API licence** is a **gating item** for a paid product — must appear in deployment secrets, legal checklist, and cost section.
- **Concurrency:** If multiple jobs incrementally update the same FAISS index and map file, you need **locking or a single writer** to avoid corruption (deployment/ops detail the current doc does not cover).

---

## 3. How this changes `DEPLOYMENT_REQUIREMENTS.md` (by section)

Below is a **checklist of documentation updates** (not implementation). The current doc assumes **users upload assets after Stage 1** (`awaiting_assets`, upload endpoints, folder layout under `assets/music/`, `assets/sfx/`, etc.). Semantic auto-resolve **narrows** mandatory uploads (e.g. more SFX/ambience filled automatically) but **does not remove** voice or curated music if you still require those.

| Section / topic | Current doc | Add or change |
|-----------------|------------|----------------|
| **§1 What you are deploying** | States the pipeline shell does not change the engines. | Qualify: **Engine 2 resolver behaviour** may change (semantic resolve + optional Freesound); **schemas** (`draft_timeline.json`, `final_timeline.json`) can stay stable as in the spec. |
| **§2 Architecture** | Celery runs three engines. | Optional box: **shared library volume** (seed + Freesound cache), **FAISS index + `index_map.json`**, **model cache path** for CLAP. |
| **§3 Server / RAM** | Table lists Engine 1 + Engine 3 buffer memory. | Add **CLAP + FAISS runtime RAM** (order of **+0.5–1.5 GB** depending on implementation and batching). Revisit **16 GB minimum** if running **2 workers × (NLP + CLAP)**. |
| **§3 Disk** | 80 GB for OS, venvs, **audio asset library**, temp. | Add **~1 GB** CLAP weights; **FAISS index** size (small vs WAV library); note **growing Freesound cache** on disk or object storage. |
| **§6 File storage** | Per-project `assets/sfx/{descriptor}/` layout. | Document **global or platform-level library** paths (seed + cache) vs per-project uploads; sync **Freesound downloads** to S3/R2 if workers are ephemeral; **backup** index + map with library. |
| **§7 API** | Heavy emphasis on asset upload. | Clarify **when uploads are still required** vs **auto-resolved**; optional admin/ops endpoint or internal job: **rebuild index**. |
| **§8 Frontend** | Asset shopping list + upload. | UX copy: resolved assets may show **CLAP score**, **source: local \| freesound**, **licence**; CC-BY **attribution** surfaced for download/legal. |
| **§10 AI / API keys** | Gemini for Engine 1. | New secret: **`FREESOUND_API_KEY`** (and note **commercial licence** contact / status). |
| **§11 Python dependencies** | Engine 2: `pydub`, `soundfile`. | Add **`msclap`**, **`faiss-cpu`** (or `faiss-gpu` if used), **`numpy`** (if not already shared), **`requests`** or official client; optional **`librosa`** if required by chosen CLAP path. Pin versions for reproducible deploys. |
| **§11 Model pre-download** | HF cache for sentence-transformers. | Add one-time **CLAP weight pre-download** step (similar to `SentenceTransformer(...)` block); extend **`HF_HOME` / cache** narrative if CLAP uses shared caches. |
| **§12 System packages** | FFmpeg, libsndfile, etc. | Usually unchanged; confirm no extra OS libs required by `msclap`/torch on your Ubuntu version. |
| **§14 Environment variables** | — | Document `FREESOUND_API_KEY`, paths for **`LIBRARY_ROOT`**, **`FAISS_INDEX_PATH`**, **`INDEX_MAP_PATH`**, **`CLAP_SIMILARITY_THRESHOLD`**, optional **`FREESOUND_COMMERCIAL_LICENCE_ACK`**. |
| **§16 Monitoring** | Stage timings. | Metrics: **CLAP search latency**, **fallback rate to Freesound**, **download failures**, **index rebuild duration**, **attribution records written**. |
| **§17 Backups** | R2 continuous. | Explicitly include **vector index + path map** with the library audio objects. |
| **§18 Cost** | R2 ~$1.50/100GB; Gemini. | **Freesound commercial fee** (TBD); marginal **storage growth** from auto-downloaded SFX; **negligible** extra compute $ if staying CPU. |
| **§19 Checklist** | Upload assets, resolve, render. | Items: **pre-build or restore FAISS index**, **verify CLAP model on disk**, **Freesound licence + key**, **legal review of CC-BY surfacing**. |

---

## 4. Integration point (codebase)

The spec’s hook **`find_best()` in `asset_engine/src/asset_engine/resolvers/library_resolver.py`** matches a natural seam: swap folder-token logic for **encode → search → threshold → optional fallback**, keep upstream/downstream contracts stable.

---

## 5. Product / workflow impact

- **Stage 1 → Stage 2:** Fewer “missing” slots if the **seed library + FAISS** cover common cues; **Freesound** fills long tail. You may still want **manual override** (upload replaces auto pick).
- **`asset_manifest.json`:** Should store **similarity score**, **provenance** (local vs Freesound), and **licence + attribution** for compliance — the deployment doc should mention **persisting manifest in DB** (`asset_manifests` table already sketched) as the **source of truth for credits**.

---

## 6. Recommendation

1. **Document** the RAM, disk, env vars, and Freesound licensing deltas in `DEPLOYMENT_REQUIREMENTS.md` as soon as you commit to Phase 1+.
2. **Implement Phase 1** without Freesound to validate quality and infra; then **Phase 2** with strict licence filters and manifest attribution.
3. **Resolve index concurrency** (file locking or queue writer) before running multiple Celery workers against one shared library path.

---

*End of note.*
