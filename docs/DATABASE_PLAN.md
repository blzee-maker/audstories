# Database plan for the initial launch

**Status:** proposal, not yet implemented. Written 2026-10-03.

The short version: AudStories already has three places where state lives, none of
them is the owner, and they disagree. This plan picks one owner, lists the defects
the split is causing right now, and splits the work into what has to land before
launch and what can wait.

---

## 1. Where data lives today

| Store | Holds | Written by | Read by |
|---|---|---|---|
| **Supabase Postgres** — [schema.sql](../schema.sql) | `projects`, `units` (+ RLS, `updated_at` triggers) | the browser, directly, from 5 pages | the browser |
| **SQLite** — `workspace/api_state.db`, [state_store.py](../backend/api/state_store.py) | `projects(id, data JSON)`, `jobs(id, data JSON)` | the API | the API, the worker |
| **Filesystem** — `workspace/projects/<id>/` | `book_metadata.json`, `chapters/`, `assets/`, `output/*.wav`, `pacing_overrides.json` | the API and both CLI stages | everything |

The backend never touches Postgres. It uses Supabase for one thing only — verifying
who a user is ([auth.py](../backend/api/auth.py)). The browser never touches SQLite.
The two `projects` tables share a primary key and duplicate seven columns (`name`,
`format`, `writer_name`, `narration_choice`, `ai_voice_provider`, `story_text`,
`status`) with no reconciliation in either direction.

Nothing is backed up. SQLite lives in a Docker volume
([docker-compose.yml](../docker-compose.yml)) and the rendered audio sits next to it.

---

## 2. What the split is costing us

These are present-tense defects, not hypotheticals.

1. **Project creation is three writes with no rollback.**
   [CreateProject.jsx:36-70](../frontend/src/pages/CreateProject.jsx#L36-L70) inserts a
   `projects` row, then a `units` row, then calls `POST /api/projects`. If the last call
   fails, the user owns a project that has no workspace and can never render. If the
   second fails, they own a project with no chapter.

2. **Pipeline status never reaches the UI's database.** The worker writes status into
   the SQLite blob. `units.status` defaults to `'draft'` in
   [schema.sql](../schema.sql) and **nothing ever updates it** — yet
   [AudioDramaDashboard.jsx:435-441](../frontend/src/pages/AudioDramaDashboard.jsx#L435-L441)
   selects and displays it. Same for `projects.total_runtime` and
   `units.duration_seconds`: read, never written.

3. **The frontend guesses column names to work around it.**
   [ProjectDetails.jsx:50-63](../frontend/src/pages/ProjectDetails.jsx#L50-L63) tries
   `runtime_seconds`, `total_runtime_seconds`, `duration_seconds` and `duration` in
   turn, then falls back to one API call per unit
   ([ProjectDetails.jsx:200](../frontend/src/pages/ProjectDetails.jsx#L200)) — an N+1
   over the filesystem to recover a number the database should be holding.

4. **Deleting a project leaks everything except the row.**
   [Profile.jsx:67-71](../frontend/src/pages/Profile.jsx#L67-L71) deletes from Postgres.
   The SQLite row and the whole `workspace/projects/<id>/` tree — story text, uploaded
   audio, finished mixes — stay on disk forever. That is both a storage leak and a
   "delete my data" problem.

5. **Ownership is enforced twice, by different rules.** Postgres has RLS keyed on
   `auth.uid()`. The API compares a `user_id` field inside its own JSON blob
   ([deps.py:15-21](../backend/api/deps.py#L15-L21)). Lose or reset the workspace volume
   and every project becomes a 404 even though the Postgres rows survive.

6. **The client picks the primary key.** `POST /api/projects` takes `project_id` from
   the request body and only rejects it if *someone else* already claimed it
   ([projects.py:50-60](../backend/api/routes/projects.py#L50-L60)). The API never checks
   that the UUID corresponds to a Postgres row the caller owns.

7. **Uploaded assets have no records at all.** Whether a requirement is satisfied is
   decided by globbing a directory for an audio extension
   ([assets.py:35-37](../backend/api/routes/assets.py#L35-L37)). There is no record of
   who uploaded what, when, how big, or whether the same file is already present — so no
   dedupe, no reuse across projects, no quota, no audit.

8. **Nothing is queryable.** Both SQLite tables are `(id, data TEXT)`. "How many renders
   failed this week", "which projects are stuck in `running`", "how much disk does this
   user hold" are all full scans plus JSON parsing in Python.

9. **No migration tooling.** `schema.sql` is documented as "run this in the SQL Editor
   once per project, safe to re-run". That works for two tables and stops working the
   first time a column has to change on a database that has real rows in it.

---

## 3. The decision

> **Supabase Postgres becomes the single owner of all metadata. The backend owns all
> writes to it. SQLite is retired. The filesystem keeps the bytes, and becomes
> disposable scratch space with durable copies in object storage.**

Why this and not the alternatives:

- **Why Postgres, not "keep SQLite and sync the two".** Supabase is already a hard
  dependency for auth and for five pages of UI. A sync job between two databases is more
  code than removing one of them, and it is the kind of code that is wrong for weeks
  before anyone notices.
- **Why the backend owns writes.** Two writers with no reconciliation is the direct cause
  of defects 1, 2 and 3. The backend has to write status and duration no matter what, so
  it is the component that must own the table. Browser *reads* can stay direct and
  RLS-protected — that keeps the UI fast and loses nothing.
- **Why keep the filesystem.** Stage 2 renders in a subprocess that needs real paths.
  That does not change. What changes is that the workspace stops being the source of
  truth: durable copies of user uploads and finished mixes go to object storage, and the
  database holds the pointers. A wiped workspace then costs a re-render, not data.

A useful side effect: once reads go through the API too, `AS_DEV_NO_AUTH=1` unlocks the
whole app rather than just the API, retiring the first entry under "Known limits" in
[CLAUDE.md](../CLAUDE.md).

---

## 4. Target schema

A sketch, not final DDL. `auth.users` is Supabase-managed.

```sql
projects
  id uuid pk, user_id uuid -> auth.users on delete cascade
  name text, format text check (format in ('drama','book'))
  writer_name text
  narration_choice text, ai_voice_provider text
  delivery_profile text                    -- today: derived in _ensure_book_metadata
  created_at, updated_at timestamptz

units                                      -- chapters / episodes
  id uuid pk, project_id uuid -> projects on delete cascade
  slug text not null                       -- the engine/filesystem identity, explicit
  name text, position int
  story_text text
  status unit_status not null default 'draft'
  duration_seconds numeric                 -- written by the worker, finally
  created_at, updated_at
  unique (project_id, slug)

jobs                                       -- replaces the SQLite blob
  id uuid pk, project_id uuid -> projects on delete cascade
  unit_id uuid -> units on delete cascade
  action text check (action in ('stage1','stage2','tts'))
  status job_status not null               -- queued|running|succeeded|failed|cancelled
  attempt int not null default 1
  error text
  locked_by text, lease_expires_at timestamptz   -- see phase 3
  queued_at, started_at, finished_at timestamptz

assets                                     -- what the user supplied, per requirement
  id uuid pk, unit_id uuid -> units on delete cascade
  requirement_id text, asset_kind text, descriptor text
  storage_path text                        -- object storage key
  bytes bigint, sha256 text, source text   -- upload | tts | library
  created_at
  unique (unit_id, requirement_id)

renders                                    -- one row per finished mix
  id uuid pk, unit_id uuid -> units on delete cascade
  job_id uuid -> jobs
  storage_path text, format text           -- wav | mp3
  duration_seconds numeric, lufs numeric, true_peak numeric
  created_at
```

Three schema decisions worth arguing about before anyone writes the migration:

- **`units.slug` becomes explicit.** Today `active_unit_slug` is set to the unit UUID
  ([projects.py:60](../backend/api/routes/projects.py#L60)), while `_sanitize_project_id`
  is duplicated across `book_cli.py`, `drama_cli.py` and `run_pipeline.py` and all three
  must agree. Storing the slug the engine actually uses makes the database and the
  directory layout verifiably consistent.
- **One status vocabulary.** SQLite uses `queued/running/failed`; Postgres `units.status`
  defaults to `'draft'`. Pick one enum, define it once, share it between API, worker and
  UI.
- **`sha256` on assets,** so the same uploaded sound is stored once per user and a
  re-upload is detectable without re-reading the file.

---

## 5. Phases

### Phase 0 — migration tooling (prerequisite, about half a day)

Adopt Supabase CLI migrations: `supabase/migrations/NNNN_*.sql`, applied with
`supabase db push`. Retire [schema.sql](../schema.sql) by making its contents migration
`0001`, so existing projects are already at that revision. This also gives a local
Postgres in Docker, which Phase 1's tests need.

### Phase 1 — launch blockers

1. **One create path.** `POST /api/projects` creates the Postgres `projects` and `units`
   rows itself, in one transaction, and returns the IDs. The browser stops inserting.
   Fixes defects 1 and 6.
2. **The worker writes status, duration and render pointers to Postgres.** Fixes defects
   2 and 3, and lets `ProjectDetails` drop both its per-unit API calls and its column
   guessing.
3. **A real delete endpoint.** `DELETE /api/projects/{id}` cascades the rows, removes the
   workspace tree and removes the storage objects. The browser calls that instead of
   deleting the row itself. Fixes defect 4.
4. **Retire SQLite.** `projects` and `jobs` move to Postgres; ownership checks read the
   `user_id` column; RLS stays as the browser's read-side guard. Fixes defects 5 and 8.
5. **`assets` and `renders` rows** written where the code currently globs directories.
   Fixes defect 7.
6. **Backups on.** Supabase Pro, for daily backups and no inactivity pausing.

### Phase 2 — object storage for audio

Supabase Storage (S3-compatible) buckets for uploaded assets and finished mixes, served
as signed URLs. The workspace becomes scratch. **Encode an MP3 alongside the WAV** for
streaming and preview: a 30-minute 48k/24-bit stereo master is roughly 500 MB, and
serving that on every play is the single largest egress cost this product has.

### Phase 3 — more than one instance

Only needed when one box stops coping. The `jobs` table already carries `locked_by` and
`lease_expires_at` for it: workers claim rows with `SELECT ... FOR UPDATE SKIP LOCKED`,
and the restart-recovery logic already in
[worker.py:40-50](../backend/api/worker.py#L40-L50) becomes a lease-expiry sweep. No
Redis and no Celery until Postgres is demonstrably the bottleneck.

---

## 6. Tests and CI

Six suites exist and CI runs all of them, and [CLAUDE.md](../CLAUDE.md) requires that
tests leave the tree clean. Moving off SQLite must not mean every API test needs a
database:

- Put Postgres access behind a repository interface, so the existing API tests run
  against an in-memory fake.
- Add **one** integration suite that skips unless `DATABASE_URL` is set, and give CI a
  Postgres service container so it runs there.
- `AS_WORKSPACE_DIR` and `--projects-root` keep working unchanged — the filesystem half
  of the story does not move in Phase 1.

---

## 7. Non-goals for launch

- Replacing the asset library's JSON index (`library/index/{kind}_index.json`). It is
  built offline by a CLI and read-only at request time; a database buys nothing yet.
- Full-text or vector search over stories or assets.
- Analytics or warehousing. Phase 1's point is that the questions in defect 8 become
  *answerable*, not that we build dashboards for them.
- Multi-tenant teams or sharing. `user_id` ownership only.

---

## 8. The one open question

Phase 2's position depends on something this document does not know: **how many
concurrent renders launch has to absorb, and whether the API will run as more than one
instance.** Single box, tens of renders a day — Phase 2 can follow launch, and the Docker
volume is adequate in the meantime. Anything more, or any plan to deploy to a platform
with ephemeral disks (Fly, Render, Cloud Run), and object storage moves into Phase 1,
because on those platforms a redeploy destroys every finished mix.
