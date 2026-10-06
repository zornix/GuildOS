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
| `DATABASE_URL` | pooler URL. **Temporary:** production Vercel still uses the demo project until a prod Supabase project exists. Required — the app runs the direct-Postgres path. |
| `JWT_SECRET` | ≥32 random chars. **Must not** be `local-dev-secret`. |
| `DEV_AUTH_BYPASS` | unset or `false`. Enables `/api/auth/dev-login` otherwise. |
| `CRON_SECRET` | non-empty; Vercel Cron sends it as `Authorization: Bearer …`. |
| `FRONTEND_URL` / `BASE_URL` | real deployed origins (CORS + generated links). |
| `MESSAGE_DELIVERY_MODE` | `dry_run` until toll-free verification clears (§6), then `twilio`. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | required when mode is `twilio`. |
| `TWILIO_MESSAGING_SERVICE_SID` *or* `TWILIO_FROM_NUMBER` | exactly one, when mode is `twilio`. Prefer the Messaging Service (§6). |
| `EMAIL_DELIVERY_MODE` | `dry_run` until the Gmail app password is set (§5a), then `smtp`. Everything automatic is email (ADR-0005). |
| `SMTP_HOST` / `SMTP_PORT` | `smtp.gmail.com` / `587`. Defaults; only set to override. |
| `SMTP_USER` / `SMTP_PASSWORD` | the Workspace mailbox and its **app password**. Required when mode is `smtp`. |
| `EMAIL_FROM` | e.g. `GuildOS <ops@chapter.org>`. Required when mode is `smtp`. |
| `EMAIL_REPLY_TO` | optional; where replies land if not `EMAIL_FROM`. |
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

There is still **no self-serve "forgot password"** — nothing takes an email
address and mails a link. The supported path is officer-assisted, and since
ADR-0005 the code is *also* emailed to the member automatically:

1. The locked-out member asks an officer.
2. The officer calls `POST /api/auth/reset-code/{member_id}`, which returns a
   one-time setup code.
3. The member gets the code by email (`RESET_CODE`, sent by the outbox drain).
   The officer also sees the plaintext once and can hand it over directly if the
   mail does not arrive.
4. The member redeems it at `POST /api/auth/redeem-setup-code` to set a new
   password.

Only the bcrypt hash of the code is stored (`member_setup_codes`, migration
0148); the plaintext is shown to the issuing officer exactly once. Codes are
single-use and short-lived, and issuing a new one invalidates the old. Because
the officer is the delivery channel, they must verify the member's identity
before issuing a code. Invites, chapter creation and roster import mint setup
codes the same way, and email them the same way (`SETUP_CODE`).

> If *every* officer of a chapter is locked out, the break-glass fallback is an
> operator running `scripts/set_officer_password.py <email>` against the prod
> database,
> which prompts for a new password and updates `members.password_hash`
> directly. Treat that as a break-glass procedure: it requires prod DB
> credentials and leaves no audit trail.

---

## 5a. Email: Gmail / Google Workspace SMTP

Decision ADR-0005: **everything automatic goes by email**, SMS is only the two
manual announcement blasts (§6). Email needs no carrier verification and no
consent record, so a chapter can run the whole product before Twilio exists.

Setup, in order:

1. **Pick the sending mailbox** — a Workspace account you control, e.g.
   `ops@yourchapter.org`. A free `@gmail.com` account works for testing.
2. **Turn on 2-step verification** for that account
   (myaccount.google.com → Security). App passwords are unavailable without it.
3. **Create an app password** (Security → App passwords). Google shows a
   16-character string once — that is `SMTP_PASSWORD`, not the account password.
4. **Set the env vars** (Vercel Production scope, and `LocalDev/.env` to test):
   `EMAIL_DELIVERY_MODE=smtp`, `SMTP_USER=ops@yourchapter.org`,
   `SMTP_PASSWORD=<app password>`, `EMAIL_FROM="GuildOS <ops@yourchapter.org>"`.
   `SMTP_HOST`/`SMTP_PORT` default to `smtp.gmail.com`/`587` (STARTTLS). The boot
   guard refuses a deploy with `smtp` mode and any of host/user/password/from
   missing.
5. **Prove it end to end**:
   `npm run email:test -- someone@example.com` (equivalently
   `python3 scripts/send_test_email.py someone@example.com`). It prints the
   sender it used or the SMTP error. It refuses to run unless
   `EMAIL_DELIVERY_MODE=smtp`.

**Send limits:** a free Gmail account is ~500 recipients/day; Google Workspace is
2,000/day. A chapter of 80 sending event-creation fan-out plus treasury
notifications stays far under that. Crossing it means moving to a transactional
mail API — that replaces the body of `api/platform/email.py::send_email` and
nothing else.

**Sender rewriting:** Gmail rewrites `From` to `SMTP_USER` unless the address is
a verified "send mail as" alias on that account. Set `EMAIL_FROM` to the mailbox
itself unless you have configured the alias.

**Failures** land on the outbox row: `no_email` means the member has no usable
address, anything else is the SMTP error verbatim. Officers see them in the
outbox surface; codes are the exception — `SETUP_CODE`/`RESET_CODE` bodies are
never rendered there, because the payload holds a live credential.

---

## 6. SMS: toll-free verified number via a Messaging Service

Decision (issue #54): **toll-free verification, not A2P 10DLC** — ~3 business
days, no monthly campaign fee. The sender is a **Messaging Service**, so the app
posts `MessagingServiceSid` and Twilio's Advanced Opt-Out handles STOP/HELP.
US carriers block unverified application-to-person traffic, so do not flip
`MESSAGE_DELIVERY_MODE=twilio` before verification is approved.

Scope since ADR-0005: SMS carries **only** the manual announcement blast and the
manual event notify blast. Everything else — codes, treasury, jobs, security,
event creation — is email (§5a), so a chapter with no Twilio account still gets
every automatic message. Full research:
`docs/research/twilio-delivery.md`.

Setup, in order:

1. **Buy a toll-free number** (Twilio console → Phone Numbers → Buy a number,
   toll-free) and submit **toll-free verification** (Messaging → Regulatory
   Compliance → Toll-Free Verification): business info, EIN, use case, sample
   message matching what the app sends (`api/*/notifications.py`), opt-in
   screenshot, volume estimate.
2. **Create a Messaging Service** (Messaging → Services) and turn on **Advanced
   Opt-Out** so STOP/HELP are handled for us.
3. **Add the toll-free number as a sender** in that Messaging Service's Sender
   Pool. Copy the service SID (`MG…`).
4. **Set the env vars** (Vercel for prod, `LocalDev/.env` locally):
   `MESSAGE_DELIVERY_MODE=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_MESSAGING_SERVICE_SID`. Leave `TWILIO_FROM_NUMBER` empty — the boot
   guard requires *exactly one* sender and rejects both being set.
5. **Smoke-test one message** from `LocalDev/`:
   `npm run sms:test -- +1YOURNUMBER "hello from GuildOS"` (equivalently
   `python3 scripts/send_test_sms.py +1YOURNUMBER "hello from GuildOS"`). It
   prints the Twilio message SID, or the full Twilio error body. It refuses to
   run unless `MESSAGE_DELIVERY_MODE=twilio`.

**Trial accounts:** a trial (unupgraded) Twilio account can only text numbers
verified in its console, prefixes every message with a trial notice, and cannot
submit toll-free verification. Upgrade to paid before step 1.

`dry_run` mode marks outbox rows as simulated and sends nothing, so the whole
product is exercisable while verification is pending.

### 6.1 Consent — the real blocker (issue #57)

Carriers require **prior express consent** before an application texts a person,
and an honored opt-out afterwards. The app enforces this itself, so an
unconsented member is never texted even if everything above is configured:

| Fact | Where it lives |
|------|----------------|
| Consent given | `members.sms_consent_at` (migration 0157) |
| Opt-out | `members.sms_opted_out_at` — set, it overrides consent |
| The rule | `api/sms_consent.py` — consented = `sms_consent_at` set **and** `sms_opted_out_at` null |

In `twilio` mode both delivery paths (the outbox drain and the inline
announcement send) close a row for an unconsented member as **`failed` with
`last_error = no_consent`** and send nothing. `dry_run` still simulates every
row, so local dev is unaffected. Every outbound body ends with
`— GuildOS for <chapter name>. Reply STOP to opt out.`

**Where consent is captured**

- **Roster CSV** — the optional `consent` column
  (`name,email,phone,role,consent`). `yes`, `y`, `true` or `1` records consent
  at import; an empty cell, any other value, or no column at all leaves it
  unset. Silence is never consent.
- **`POST /api/chapters`** — `sms_consent: true` in the body records it for the
  first officer (the signup form's opt-in checkbox).
- **`POST /api/auth/invite`** — `sms_consent: true` applies to every address in
  that batch.
- **`POST /api/members/me/sms-consent`** — a signed-in member opting themselves
  in; also clears any prior opt-out.

**What the pilot chapter must do before you import their roster**

1. Collect a written opt-in from every member — a signed form or a digital form
   with an **unchecked** SMS box, naming GuildOS as the sender, the message
   types (dues reminders, event and job notifications, chapter announcements),
   "message and data rates may apply", and "reply STOP to opt out".
2. Keep those forms. If a carrier files a complaint, they are the evidence.
3. Fill the CSV's `consent` column with `yes` **only** for members who signed.
   Everyone else imports without consent and simply is not texted until they
   opt in themselves in the app.

**Inbound webhook (STOP / START / HELP)**

Paste this into the Messaging Service → Integration → "Incoming Messages", as a
webhook, `HTTP POST`:

```
https://<your-production-domain>/api/twilio/inbound
```

It must match `BASE_URL` exactly, including scheme and any trailing path —
the URL is part of the `X-Twilio-Signature` HMAC, so a mismatch makes every
callback a 403. The endpoint has no JWT; the signature (HMAC-SHA1 over
`TWILIO_AUTH_TOKEN`) is its only authentication, and it fails closed when that
token is unset.

- `STOP` / `STOPALL` / `UNSUBSCRIBE` / `CANCEL` / `END` / `QUIT` → stamps
  `sms_opted_out_at` on every member holding that number.
- `START` / `YES` / `UNSTOP` → clears the opt-out and records fresh consent.
- `HELP` → replies with one line of TwiML.

Leave **Advanced Opt-Out** on in the Messaging Service. Twilio still handles the
carrier-level STOP — it stops delivering to that number and sends the
confirmation reply itself. This webhook exists so *our* database knows too;
without it the product keeps queueing rows for a member who will never receive
them and shows an officer no reason why.

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

## Before the next production deploy

This checklist is for the operator. Syncing `Prod/`, migrating production,
applying the demo purge, and deploying each require explicit user approval.
Complete waves 1–4 and the full suite before the production sync; add the CI
`build_prod.sh --check` step only after that sync (decision D22).

1. Read production migration state with
   `SELECT name FROM schema_migrations ORDER BY 1`. Record the result and date
   in `LocalDev/docs/ops/prod-migration-state.md`.
2. Take a Supabase backup and record its time.
3. Put the production project ref in `scripts/db_guard.py:PROD_PROJECT_REFS`.
4. If production history contains only the two old `Prod/migrations` files,
   do not run `migrate:prod`: the runner refuses this history by design. Plan
   the cut-over separately and test restore-then-migrate on a copy first.
5. In Vercel, set `BASE_URL` and `FRONTEND_URL` to the public origins; confirm
   `JWT_SECRET`, `CRON_SECRET`, and `DATABASE_URL`; leave `DEV_AUTH_BYPASS`
   unset and ensure `APP_ENV` is not `local` or `test`.
6. In Supabase, confirm the Data API is disabled and record backup retention
   and PITR status in this runbook's backup section.
7. Locally, add `APP_ENV=local` to `LocalDev/.env` if absent. Delete the nine
   unused names from the stream 13 report: `ESCALATION_DELAY_MINUTES`,
   `FEATURE_SECRETARY_COMMS`, `FEATURE_VP_OPERATIONS`,
   `MESSAGE_WEBHOOK_SECRET`, `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`,
   `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_URL`.
