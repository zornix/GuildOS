# Change Audit Since Last Commit

Date: 2026-04-20  
Scope: Uncommitted changes in working tree compared to `HEAD`.

## Snapshot

- Modified tracked files: 12
- New untracked files: 8
- Net tracked diff: 161 insertions, 58 deletions

## What Was Done

### 1) Backend API and Config

- Enabled tolerant env loading in `api/config.py` by setting `extra = "ignore"` in settings config.
- Registered a new Operations router in `api/index.py`.
- Added new Operations endpoints in `api/routes/operations.py`:
  - `GET /api/operations/templates`
  - `POST /api/operations/events/{event_id}/apply-template/{template_id}`
  - `GET /api/operations/events/{event_id}/readiness`
- Added Operations service logic in `api/services/operations.py` for:
  - Template listing with role/task expansion
  - Idempotent template application to events
  - Readiness percentage calculation from task completion

### 2) Database Schema and Migrations

- Updated `migrations/0001_initial_schema.sql`:
  - Renamed event columns from `event_date`/`event_time` to `date`/`time`
  - Updated date index name accordingly
  - Added `checkin_links` table and indexes
- Reworked `migrations/0002_link_members_auth_id.sql`:
  - Adds `members.auth_id` + index safely with `IF NOT EXISTS`
  - Wraps auth linkage update in a `DO` block that runs only if `auth.users` exists
- Added `migrations/0003_operations_engine.sql`:
  - Introduces operations engine tables (`event_templates`, template roles/tasks, event roles/tasks, post-event reports)
  - Adds constraints/indexes and dedupe unique indexes
  - Seeds global starter templates (Party, Philanthropy, Chapter Meeting)

### 3) Local Dev and Runtime Tooling

- Expanded `deploy/local-dev.sh`:
  - Added reusable `ensure_env_key` helper
  - Auto-populates feature flags and messaging defaults in `.env`
  - Auto-populates frontend env defaults in `fratos/.env.local`
  - Added optional seed execution path via `SEED_LOCAL_DB=1`
  - Updated startup output to include seed command hint
- Updated `package.json` scripts:
  - Added `dev`, `dev:seed`, `migrate`, `seed`, `preflight`, `test:e2e`
- Updated `docker-compose.yml`:
  - Removed fixed container name
  - Removed direct mount of migration SQL bootstrap file

### 4) Seed and Test Adjustments

- Updated JWT subject usage in `scripts/seed.py`:
  - Token generation now uses `member_id` (not `auth_id`)
  - Updated printed sample token generation to use member IDs
- Updated Playwright fixture callback naming in `fratos/e2e/fixtures/auth.ts`:
  - Replaced `use` callback variable with `runFixture` for both fixtures

### 5) Documentation and Environment Specs

- Expanded root workspace doc in `README.md` with structure, run commands, and service URLs.
- Updated product README in `README.MD`:
  - Added Operations API surface to endpoint table
  - Documented feature flags and Secretary messaging env vars
- Updated deployment docs in `deploy/README.md`:
  - Added VP/Secretary frontend feature flags
  - Added dry-run messaging env defaults and live-provider env requirements
  - Updated local-dev script behavior steps
- Added `.env.example` with complete local defaults, feature flags, and messaging env placeholders.
- Added planning/audit docs:
  - `docs/VP_SECRETARY_FEATURE_PREP.md`
  - `docs/WEBSITE_AUDIT.md`
  - `Prod/docs/GUILDOS_FOLDER_FEATURE_AUDIT.md`
  - `Prod/docs/WEBSITE_AUDIT.md`

## File Inventory

### New Files

- `.env.example`
- `api/routes/operations.py`
- `api/services/operations.py`
- `docs/VP_SECRETARY_FEATURE_PREP.md`
- `docs/WEBSITE_AUDIT.md`
- `migrations/0003_operations_engine.sql`
- `../Prod/docs/GUILDOS_FOLDER_FEATURE_AUDIT.md`
- `../Prod/docs/WEBSITE_AUDIT.md`

### Modified Files

- `README.MD`
- `README.md`
- `api/config.py`
- `api/index.py`
- `deploy/README.md`
- `deploy/local-dev.sh`
- `docker-compose.yml`
- `fratos/e2e/fixtures/auth.ts`
- `migrations/0001_initial_schema.sql`
- `migrations/0002_link_members_auth_id.sql`
- `package.json`
- `scripts/seed.py`
