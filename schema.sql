-- AudStories — Supabase schema
-- Run this in Supabase Dashboard → SQL Editor once per project.
-- Safe to re-run: all statements use IF NOT EXISTS / OR REPLACE.

-- ─────────────────────────────────────────────
-- projects
-- ─────────────────────────────────────────────
create table if not exists projects (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  name             text not null,
  format           text not null check (format in ('drama', 'book')),
  writer_name      text,
  narration_choice text not null default 'self' check (narration_choice in ('self', 'ai', 'professional')),
  ai_voice_provider text default 'google',
  total_runtime    text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- keep updated_at current automatically
create or replace function _set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_projects_updated_at on projects;
create trigger set_projects_updated_at
  before update on projects
  for each row execute function _set_updated_at();

-- ─────────────────────────────────────────────
-- units  (chapters / episodes)
-- ─────────────────────────────────────────────
create table if not exists units (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references projects(id) on delete cascade,
  name             text not null,
  status           text not null default 'draft',
  story_text       text,
  duration_seconds numeric,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

drop trigger if exists set_units_updated_at on units;
create trigger set_units_updated_at
  before update on units
  for each row execute function _set_updated_at();

-- ─────────────────────────────────────────────
-- Row-Level Security
-- ─────────────────────────────────────────────
alter table projects enable row level security;
alter table units    enable row level security;

-- projects: full access to own rows only
drop policy if exists "projects_owner" on projects;
create policy "projects_owner" on projects
  for all using (auth.uid() = user_id);

-- units: full access when the parent project belongs to the caller
drop policy if exists "units_owner" on units;
create policy "units_owner" on units
  for all using (
    exists (
      select 1 from projects
      where projects.id = units.project_id
        and projects.user_id = auth.uid()
    )
  );
