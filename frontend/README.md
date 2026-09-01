# AudStories — frontend

React + Vite single-page app for the AudStories pipeline. See the
[project README](../README.md) for what the system does and how it fits together.

## Requires a Supabase project

Unlike the backend, this app **cannot run without Supabase**. Several pages read and write
the `projects` and `units` tables directly rather than going through the API:

- `pages/AudioDramaDashboard.jsx`
- `pages/CreateProject.jsx`
- `pages/ProjectDetails.jsx`
- `pages/ProvideStory.jsx`
- `pages/Profile.jsx`

So the backend's `AS_DEV_NO_AUTH` shortcut does not help here. Moving that storage behind
the API would remove the dependency and is the natural next change.

To evaluate the pipeline without setting up an account, use the API's interactive docs at
<http://localhost:8000/docs> instead.

## Setup

From the repo root, `./setup.sh` or `.\setup.ps1` seeds `frontend/.env` from
`.env.example`. Fill it in:

```
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=...
VITE_API_BASE_URL=http://localhost:8000
```

Run [`schema.sql`](../schema.sql) once in your Supabase SQL editor to create the tables
with row-level security.

```bash
npm install
npm run dev      # http://localhost:5173
```

The backend must be running separately — see [SETUP.md](../SETUP.md).

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint |
| `npm test` | Vitest, one shot |
| `npm run test:watch` | Vitest in watch mode |

## Testing notes

Vitest + React Testing Library + jsdom. Two things that trip people up:

- **Test files must `import React`** — the app uses the classic JSX runtime.
- `vitest.config.js` deliberately omits the Tailwind v4 plugin; it is build-only and
  loading it under jsdom fails.

## Stack

React 19, react-router-dom 7, Vite 8, Tailwind CSS 4, wavesurfer.js 7,
`@supabase/supabase-js` 2.
