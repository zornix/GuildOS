# Operations runbook

Everything an operator needs to run GuildOS in production. Terse on purpose —
each section is a procedure, not an explanation. Deep dives live in
`docs/ARCHITECTURE.md` and `docs/adr/`.

Two databases, both Supabase projects reached over the pooler (ADR-0002, there
is no local Docker DB):

| | env var | who reads it |
|---|---|---|
| demo / dev | `DATABASE_URL` | the app, `npm run migrate`, `npm run seed`, pytest |
| production | `PROD_DATABASE_URL` | `migrate_db.py --prod` and `provision_chapter.py --prod` only |

`scripts/db_guard.py` is the fail-closed gate for both: anything that is not the
demo ref or a local host is refused, and prod paths refuse entirely until
`PROD_PROJECT_REFS` is filled in that file (see below).

---

## 0. One-time setup (not yet done)

1. **Fill `PROD_PROJECT_REFS`** in `scripts/db_guard.py`. The ref is in the
   Supabase dashboard: production project → Settings → General → Reference ID.
   Until this is done, `npm run migrate:prod`, `provision_chapter.py --prod`,
   and the `Migrate production database` workflow all refuse to run.
2. **Set the `PROD_DATABASE_URL` repository secret** (GitHub → Settings →
   Secrets and variables → Actions) to the prod pooler URL.
3. **Set the Vercel production env vars** — see the checklist in §4.

---

## 1. Deploy order — schema first, always

Nothing applies migrations automatically. `vercel.json` has no `buildCommand`
or install hook, so **code ships ahead of schema by default**. Migrations are
forward-only; there are no down-migrations.

For any change that adds or alters schema:

1. Merge/queue the migration file (`migrations/NNNN_*.sql`) — never edit an
   already-applied migration, always add a new numbered file.
2. Run **Actions → "Migrate production database" → Run workflow**, typing
   `migrate-prod` in the confirm box. It runs
   `python3 scripts/migrate_db.py --prod --yes` against `PROD_DATABASE_URL`.
3. Confirm the log lists the expected files under `applied:`.
4. *Then* merge/deploy the application code that depends on the new schema.

Rules that follow from this:

- Migrations must be **backward compatible with the currently deployed code**
  (add columns nullable or with defaults; drop columns in a later release).
- If a migration fails, the runner rolls that file back and stops. The files
  before it stay applied. Fix forward with a new migration — never hand-edit
  `schema_migrations`.
- Rolling back code is easy (Vercel redeploy); rolling back schema is not. That
  asymmetry is why schema goes first and stays additive.

Sanity check without applying anything: `python3 scripts/check_prod_status.py`.

---

## 2. Backup and restore

**Verify the plan first.** In the Supabase dashboard → Database → Backups,
confirm what the current plan actually gives you: daily backup retention and
whether Point-in-Time Recovery (PITR) is enabled. Free/Pro defaults differ, and
PITR is usually an add-on. Write the answer down here once it is confirmed:

- Retention: _TBD — confirm in dashboard_
- PITR enabled: _TBD — confirm in dashboard_

**Why this matters more than usual:** `big_ledger` and `audit_logs` are
append-only with `DELETE`-blocking triggers. Bad financial data cannot be
deleted — it is corrected by appending reversal rows, or, in a genuine
corruption event, by restoring the database. There is no third option.

### Manual dump (before any risky migration, and quarterly for the drill)

```bash
# Full compressed dump. Takes the pooler URL; never commit the file.
pg_dump -Fc --no-owner --no-privileges \
  "$PROD_DATABASE_URL" \
  -f "prod-$(date +%F).dump"

# Schema only, useful for diffing against migrations/
pg_dump --schema-only --no-owner "$PROD_DATABASE_URL" -f "prod-schema-$(date +%F).sql"
```

### Quarterly restore drill

A backup nobody has restored is not a backup. Once a quarter:

```bash
# 1. Create a scratch Supabase project (or a local database) and export its URL.
export SCRATCH_URL=postgresql://...

# 2. Restore into it.
pg_restore --no-owner --no-privileges --clean --if-exists \
  -d "$SCRATCH_URL" "prod-$(date +%F).dump"

# 3. Verify: row counts on the tables that matter, and that migrations agree.
psql "$SCRATCH_URL" -c "SELECT count(*) FROM chapters;" \
                    -c "SELECT count(*) FROM members;" \
                    -c "SELECT count(*) FROM big_ledger;" \
                    -c "SELECT max(name) FROM schema_migrations;"

# 4. Delete the scratch project. Record the drill date and outcome below.
```

- Last restore drill: _never — run one_

---

## 3. Onboarding a chapter

There is no signup or onboarding UI, and no API endpoint writes to `chapters`
(GTM checklist 3.1). For the first chapters, use the vetted script — not
hand-written SQL.

```bash
# Demo (uses DATABASE_URL; require_demo refuses anything but demo/localhost)
python3 scripts/provision_chapter.py \
  --name "Alpha Beta" \
  --organization "TKE" \
  --school "State University" \
  --officer-email jane@example.edu \
  --officer-name "Jane Roe" \
  --officer-phone +15551234567

# Production (uses PROD_DATABASE_URL, then asks you to type the prod project ref)
python3 scripts/provision_chapter.py --prod \
  --name "Alpha Beta" \
  --organization "TKE" \
  --school "State University" \
  --officer-email jane@example.edu \
  --officer-name "Jane Roe"
```

What it does, in one transaction: inserts the `chapters` row, inserts the first
officer into `members` (`role='officer'`, `status='active'`, email lowercased,
phone optional and validated as E.164), and grants the `officer` role in
`member_roles`. The password is prompted for interactively (hidden, min 8
chars, bcrypt-hashed) — never pass it in argv or env.

It **refuses and exits 1** if a chapter with that name already exists, or if the
officer email is already taken (`members.email` is globally unique). It never
upserts and never deletes; if it fails, the whole transaction rolls back and
nothing was created. To add more officers to an existing chapter, use the
in-app roster/invite flow, not this script.

Hand the officer their password out of band. They can change it via
`POST /api/auth/set-password` once signed in.

---

## 4. Env var checklist for a new deploy

`.env.example` is the tracked reference for every variable and what reads it.
Set these in the Vercel project (Production scope):

| Variable | Note |
|---|---|
| `DATABASE_URL` | prod pooler URL. Required — the app runs the direct-Postgres path. |
| `JWT_SECRET` | ≥32 random chars. **Must not** be `local-dev-secret`. |
| `DEV_AUTH_BYPASS` | unset or `false`. Enables `/api/auth/dev-login` otherwise. |
| `CRON_SECRET` | non-empty; Vercel Cron sends it as `Authorization: Bearer …`. |
| `FRONTEND_URL` / `BASE_URL` | real deployed origins (CORS + generated links). |
| `MESSAGE_DELIVERY_MODE` | `dry_run` until 10DLC clears (§6), then `twilio`. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | required when mode is `twilio`. |
| `SENTRY_DSN` | enables error reporting; empty disables it (§7). |
| `CHECKIN_LINK_TTL_MINUTES` | defaults to 10. |

`PROD_DATABASE_URL` is **not** a Vercel variable — it lives only in the GitHub
secret and, optionally, an operator's local `.env`. The app must never read it.

**The boot guard will refuse a bad config.** `api/index.py` checks the
production config at import time and raises, failing the deploy rather than
serving traffic, when `JWT_SECRET` is still the local default, `DATABASE_URL`
is unset, or `DEV_AUTH_BYPASS` is truthy. A failed deploy with
`Refusing to boot in production — fix: …` in the Vercel logs means exactly this
— fix the variable and redeploy. Preview deployments are deliberately not
guarded.

---

## 5. Password reset (officer-assisted)

There is no email provider, so there is **no self-serve "forgot password"**
(GTM checklist 3.3). The supported path is officer-assisted:

1. The locked-out member asks an officer.
2. The officer calls `POST /api/auth/reset-code/{member_id}`, which returns a
   one-time setup code.
3. The officer hands the code to the member out of band (in person, SMS, group
   chat).
4. The member redeems it at `POST /api/auth/redeem-setup-code` to set a new
   password.

Only the bcrypt hash of the code is stored (`member_setup_codes`, migration
0148); the plaintext is shown to the issuing officer exactly once. Codes are
single-use and short-lived, and issuing a new one invalidates the old. Because
the officer is the delivery channel, they must verify the member's identity
before issuing a code.

> If *every* officer of a chapter is locked out, the break-glass fallback is an
> operator running `scripts/set_officer_password.py <email>` against the prod
> database,
> which prompts for a new password and updates `members.password_hash`
> directly. Treat that as a break-glass procedure: it requires prod DB
> credentials and leaves no audit trail.

---

## 6. SMS: A2P 10DLC registration must precede go-live

**Do not set `MESSAGE_DELIVERY_MODE=twilio` before 10DLC registration is
complete.** US carriers block unregistered application-to-person traffic from
long codes, silently or with 30007 errors. Registration is not instant —
brand vetting plus campaign approval typically takes days to weeks — so start
it in the Twilio console (Messaging → Regulatory Compliance → A2P 10DLC) well
before launch:

1. Register the **Brand** (legal entity, EIN, address).
2. Register a **Campaign** — use case "Mixed"/"Low Volume Mixed" fits chapter
   announcements, attendance links, and dues reminders. Sample messages must
   match what the app actually sends (see `api/*/notifications.py`).
3. Attach the sending number (`TWILIO_FROM_NUMBER`, E.164) to the campaign.
4. Only once the campaign is **approved**: set `MESSAGE_DELIVERY_MODE=twilio`
   plus the three `TWILIO_*` vars, and redeploy.

`dry_run` mode marks outbox rows as simulated and sends nothing, so the whole
product is exercisable while registration is pending. Every campaign needs
working opt-out (STOP) handling — verify before the first real send.

---

## 7. Monitoring

- **Uptime:** point an external monitor (UptimeRobot, Better Stack, Checkly) at
  `GET /api/health` on the production domain, every 1–5 minutes. It is a real
  database ping, not a static 200, so it catches DB outages and exhausted
  pooler connections — not just a dead function. Alert on two consecutive
  failures.
- **Errors:** set `SENTRY_DSN` in the Vercel production env to enable error
  reporting (`api/observability.py`; `sentry-sdk[fastapi]` is a dependency).
  Empty — the local default — makes it a no-op. Leave it unset and unhandled
  exceptions become a plain 500 whose traceback exists only in Vercel logs,
  unalerted (GTM checklist 3.4).
- **Cron:** Vercel Cron jobs must be declared in the **project-root**
  `vercel.json`; `api/vercel.json` is never read. Any cron endpoint must check
  `CRON_SECRET` before it does work.
- **After every prod migration**, check `/api/health` and the Vercel function
  logs for boot-guard errors before walking away.

---

## 8. CI

`.github/workflows/ci.yml` runs on every push/PR touching `LocalDev/**`:

- **backend** — spins up `postgres:16-alpine`, applies all migrations with
  `scripts/migrate_db.py`, then runs `python3 -m pytest`. This is also the only
  routine check that the full migration chain applies cleanly from zero.
- **frontend** — `npm ci && npm run lint && npm run test:unit && npm run build`
  in `fratos/`. Playwright e2e is excluded; it needs a live API + DB stack.

`.github/workflows/migrate-prod.yml` is manual-dispatch only (§1). It is the
only workflow that can touch production.
