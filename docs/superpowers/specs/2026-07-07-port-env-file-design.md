# Per-Machine Port Env File — Design

**Problem:** `FRONTEND_PORT`/`BACKEND_PORT` (introduced earlier today to dodge the
planeswalker Docker stack's squatting of :5173/:8000) had to be typed on every
`task` invocation — easy to forget mid-demo, at which point requests silently land
on the wrong app.

**Decision:** A repo-root `.env` (gitignored) loaded by the Taskfile via go-task's
native `dotenv: [".env"]`, with a committed `.env.example` template. OS environment
variables take precedence over dotenv values in Task, so one-off shell overrides
(`FRONTEND_PORT=5201 task dev`) still win.

## Changes

1. `Taskfile.yml` — `dotenv: [".env"]` at the top level.
2. `.env.example` (committed) — `FRONTEND_PORT=5173`, `BACKEND_PORT=8000`, with
   comments pointing at the `REDIRECT_URI`/`FRONTEND_URL` sync + client
   re-registration steps a port change requires.
3. `.env` (gitignored via a root-anchored `/.env` pattern, so `docker/.env` and
   `backend/.env.*` rules are unaffected) — this machine's real values
   (`FRONTEND_PORT=5199`, `BACKEND_PORT=8010`).
4. README — port paragraphs now lead with the `.env` mechanism; env-file table
   gains the two new rows.

## Deliberate limits

- The root `.env` reaches only `task` commands. A bare `npm run dev` or `uvicorn`
  still needs shell variables; documented rather than adding a second env-loading
  mechanism to Vite/pydantic.
- FHIR-instance config (`backend/.env.*`) and Docker secrets (`docker/.env`) stay
  where they are — the root file holds per-machine port choices only.

## Verification (2026-07-07)

- `git check-ignore .env` matches the new `/.env` rule.
- Plain `task backend:serve` / `task frontend:dev` served on :8010/:5199 from the
  dotenv values.
- `FRONTEND_PORT=5201 task frontend:dev` served on :5201 (shell wins over dotenv).
